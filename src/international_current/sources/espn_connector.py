from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.international_current.sources.source_fetching import FetchResult, fetch_public_source, read_local_source, write_fetch_metadata
from src.international_current.team_name_normalization import normalize_team_pair


ESPN_URLS = [
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
]


def _competitor_name(item: dict[str, Any]) -> str:
    team = item.get("team") or {}
    return str(team.get("displayName") or team.get("name") or item.get("displayName") or "")


def parse_espn_fixture_rows(text: str, *, source_url: str = "") -> pd.DataFrame:
    if not text.strip():
        return pd.DataFrame()
    payload = json.loads(text)
    events = payload.get("events") or payload.get("matches") or []
    rows = []
    for event in events:
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        home_item = next((item for item in competitors if item.get("homeAway") == "home"), competitors[0] if competitors else {})
        away_item = next((item for item in competitors if item.get("homeAway") == "away"), competitors[1] if len(competitors) > 1 else {})
        home, away, warnings = normalize_team_pair(_competitor_name(home_item), _competitor_name(away_item))
        if not home or not away:
            continue
        rows.append({
            "match_date": str(event.get("date") or "")[:10],
            "kickoff_time": str(event.get("date") or "")[11:16],
            "competition": (payload.get("leagues") or [{}])[0].get("name") or "FIFA World Cup",
            "round_name": event.get("season", {}).get("slug") or "",
            "group_name": "",
            "home_team": home,
            "away_team": away,
            "neutral_site": str(competition.get("neutralSite", "unknown")),
            "venue": (competition.get("venue") or {}).get("fullName") or "",
            "source_name": "espn_scoreboard",
            "source_url": event.get("links", [{}])[0].get("href") if event.get("links") else source_url,
            "source_tier": "real",
            "source_status": (competition.get("status") or {}).get("type", {}).get("name") or "scheduled",
            "is_sample_data": False,
            "reliability_status": "fetched_public_source",
            "fixture_confidence": "medium",
            "warnings": " | ".join(warnings + ["ESPN public scoreboard is fixture/scoreboard data, not event/tracking style."]),
        })
    return pd.DataFrame(rows)


def seed_espn_fixtures(
    *,
    cache_dir: str | Path,
    allow_network: bool = False,
    local_paths: list[str | Path] | None = None,
    max_sources: int | None = None,
) -> tuple[pd.DataFrame, list[FetchResult]]:
    frames: list[pd.DataFrame] = []
    fetches: list[FetchResult] = []
    sources: list[tuple[str | Path, bool]] = [(path, False) for path in (local_paths or [])] + [(url, True) for url in ESPN_URLS]
    if max_sources is not None:
        sources = sources[:max_sources]
    for locator, is_url in sources:
        fetch, text = fetch_public_source(source_name="espn_scoreboard", source_url=str(locator), raw_dir=Path(cache_dir) / "raw", allow_network=allow_network) if is_url else read_local_source("espn_scoreboard", locator)
        try:
            frame = parse_espn_fixture_rows(text, source_url=str(locator)) if text else pd.DataFrame()
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
