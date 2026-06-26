from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.international_current.sources.source_fetching import FetchResult, fetch_public_source
from src.international_current.team_name_normalization import normalize_team_pair


HISTORICAL_RESULT_COLUMNS = [
    "match_date",
    "competition",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "neutral_site",
    "source_name",
    "source_url",
    "source_status",
    "is_result",
    "warning",
]

OPENFOOTBALL_WORLD_CUP_URLS = [
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2018/worldcup.json",
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2022/worldcup.json",
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json",
]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=HISTORICAL_RESULT_COLUMNS)


def _score(value: Any) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(number) else float(number)


def _normalize_frame(frame: pd.DataFrame, *, source_status: str = "cache_hit") -> pd.DataFrame:
    if frame.empty:
        return _empty()
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        home_raw = str(row.get("home_team") or row.get("home") or row.get("team1") or "").strip()
        away_raw = str(row.get("away_team") or row.get("away") or row.get("team2") or "").strip()
        home, away, warnings = normalize_team_pair(home_raw, away_raw)
        home_goals = _score(row.get("home_goals") if "home_goals" in row else row.get("score1"))
        away_goals = _score(row.get("away_goals") if "away_goals" in row else row.get("score2"))
        match_date = str(row.get("match_date") or row.get("date") or "")[:10]
        if not match_date or not home or not away or home_goals is None or away_goals is None:
            continue
        rows.append({
            "match_date": match_date,
            "competition": row.get("competition") or row.get("competition_name") or "FIFA World Cup",
            "home_team": home,
            "away_team": away,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "neutral_site": row.get("neutral_site", "true"),
            "source_name": row.get("source_name") or "local_historical_results",
            "source_url": row.get("source_url") or "",
            "source_status": row.get("source_status") or source_status,
            "is_result": True,
            "warning": row.get("warning") or "Historical result row; no current style inputs attached." + (" | " + " | ".join(warnings) if warnings else ""),
        })
    return pd.DataFrame(rows, columns=HISTORICAL_RESULT_COLUMNS)


def _parse_openfootball_json(text: str, source_url: str, status: str) -> pd.DataFrame:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _empty()
    matches = payload.get("matches", payload if isinstance(payload, list) else [])
    rows: list[dict[str, Any]] = []
    for row in matches:
        score = row.get("score") or {}
        full_time = score.get("ft") if isinstance(score, dict) else None
        home_goals = row.get("score1") if row.get("score1") is not None else row.get("home_goals")
        away_goals = row.get("score2") if row.get("score2") is not None else row.get("away_goals")
        if (home_goals is None or away_goals is None) and isinstance(full_time, list) and len(full_time) >= 2:
            home_goals, away_goals = full_time[0], full_time[1]
        rows.append({
            "match_date": row.get("date"),
            "competition": payload.get("name") or payload.get("competition") or "FIFA World Cup",
            "home_team": row.get("team1") or row.get("home_team"),
            "away_team": row.get("team2") or row.get("away_team"),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "neutral_site": "true",
            "source_name": "openfootball_historical_worldcup",
            "source_url": source_url,
            "source_status": status,
        })
    return _normalize_frame(pd.DataFrame(rows), source_status=status)


def load_historical_results(cache_dir: str | Path = "data/source_cache/current_international") -> pd.DataFrame:
    root = Path(cache_dir)
    parsed = root / "parsed" / "historical_results.csv"
    frames: list[pd.DataFrame] = []
    if parsed.exists():
        frames.append(_normalize_frame(pd.read_csv(parsed), source_status="parsed_cache_hit"))
    local_dir = root / "historical_results"
    if local_dir.exists():
        for path in sorted(local_dir.glob("*.csv")):
            frames.append(_normalize_frame(pd.read_csv(path), source_status="local_result_cache_hit"))
    if not frames:
        return _empty()
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(["match_date", "home_team", "away_team", "competition"], keep="first")
    return out.sort_values(["match_date", "home_team", "away_team"]).reset_index(drop=True)


def seed_historical_results(
    *,
    start_date: str,
    end_date: str,
    allow_network: bool = False,
    force_refresh: bool = False,
    max_matches: int | None = None,
    cache_dir: str | Path = "data/source_cache/current_international",
) -> dict[str, Any]:
    root = Path(cache_dir)
    parsed_path = root / "parsed" / "historical_results.csv"
    fetches: list[FetchResult] = []
    frames: list[pd.DataFrame] = []
    if parsed_path.exists() and not force_refresh:
        frame = load_historical_results(root)
        return {"results": frame.head(max_matches) if max_matches else frame, "fetches": fetches, "parsed_path": parsed_path, "source_status_counts": {"parsed_cache_hit": len(frame)}}

    if not force_refresh:
        frames.append(load_historical_results(root))
    for url in OPENFOOTBALL_WORLD_CUP_URLS:
        fetch, text = fetch_public_source(
            source_name="openfootball_historical_worldcup",
            source_url=url,
            raw_dir=root / "historical_results" / "raw",
            allow_network=allow_network,
        )
        fetches.append(fetch)
        if text:
            frames.append(_parse_openfootball_json(text, url, fetch.status))
    out = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True) if any(not frame.empty for frame in frames) else _empty()
    if not out.empty:
        out = out.drop_duplicates(["match_date", "home_team", "away_team", "competition"], keep="first")
        out = out[(pd.to_datetime(out["match_date"], errors="coerce") >= pd.to_datetime(start_date, errors="coerce")) & (pd.to_datetime(out["match_date"], errors="coerce") <= pd.to_datetime(end_date, errors="coerce"))]
    if max_matches:
        out = out.head(max_matches)
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    if force_refresh and parsed_path.exists():
        parsed_path.unlink()
    out.to_csv(parsed_path, index=False)
    return {
        "results": out,
        "fetches": fetches,
        "parsed_path": parsed_path,
        "source_status_counts": dict(pd.Series([fetch.status for fetch in fetches]).value_counts()) if fetches else {},
    }
