from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.international_current.sources.source_fetching import FetchResult, fetch_public_source, read_local_source, write_fetch_metadata
from src.international_current.team_name_normalization import normalize_team_pair


OPENFOOTBALL_URLS = [
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json",
    "https://raw.githubusercontent.com/openfootball/worldcup/master/2026/worldcup.json",
]


def _rows_from_payload(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped[0] in "[{":
        payload = json.loads(stripped)
        return payload.get("matches", payload if isinstance(payload, list) else [])
    return list(csv.DictReader(io.StringIO(text)))


def parse_openfootball_rows(text: str, *, source_name: str = "openfootball_worldcup", source_url: str = "") -> pd.DataFrame:
    rows = []
    for index, row in enumerate(_rows_from_payload(text)):
        home_raw = row.get("home_team") or row.get("team1") or row.get("home") or row.get("homeTeam") or ""
        away_raw = row.get("away_team") or row.get("team2") or row.get("away") or row.get("awayTeam") or ""
        home, away, warnings = normalize_team_pair(str(home_raw), str(away_raw))
        if not home or not away:
            continue
        rows.append({
            "match_date": row.get("match_date") or row.get("date") or "",
            "kickoff_time": row.get("kickoff_time") or row.get("time") or "",
            "competition": row.get("competition") or "FIFA World Cup",
            "round_name": row.get("round_name") or row.get("round") or "",
            "group_name": row.get("group_name") or row.get("group") or "",
            "home_team": home,
            "away_team": away,
            "neutral_site": row.get("neutral_site", "true"),
            "venue": row.get("venue") or "",
            "source_name": source_name,
            "source_url": row.get("source_url") or source_url,
            "source_tier": "real",
            "source_status": row.get("status") or "scheduled",
            "is_sample_data": False,
            "reliability_status": "fetched_public_source",
            "fixture_confidence": "medium",
            "warnings": " | ".join(warnings + ["OpenFootball-style source is fixture/result structure only."]),
        })
    return pd.DataFrame(rows)


def seed_openfootball_fixtures(
    *,
    cache_dir: str | Path,
    allow_network: bool = False,
    local_paths: list[str | Path] | None = None,
    max_sources: int | None = None,
) -> tuple[pd.DataFrame, list[FetchResult]]:
    frames: list[pd.DataFrame] = []
    fetches: list[FetchResult] = []
    sources: list[tuple[str, str | Path, bool]] = []
    for path in local_paths or []:
        sources.append(("openfootball_worldcup", path, False))
    for url in OPENFOOTBALL_URLS:
        sources.append(("openfootball_worldcup", url, True))
    if max_sources is not None:
        sources = sources[:max_sources]
    for source_name, locator, is_url in sources:
        fetch, text = fetch_public_source(source_name=source_name, source_url=str(locator), raw_dir=Path(cache_dir) / "raw", allow_network=allow_network) if is_url else read_local_source(source_name, locator)
        try:
            frame = parse_openfootball_rows(text, source_name=source_name, source_url=str(locator)) if text else pd.DataFrame()
            fetch.status = "success" if len(frame) else fetch.status if fetch.status in {"blocked", "not_found", "cache_miss"} else "empty"
            write_fetch_metadata(fetch, len(frame))
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:
            fetch.status = "parse_error"
            fetch.error_message = str(exc)
            write_fetch_metadata(fetch, 0)
        fetches.append(fetch)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), fetches
