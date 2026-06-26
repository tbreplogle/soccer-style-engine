from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.international_current.sources.international_football_connector import parse_international_football_ratings
from src.international_current.sources.source_fetching import FetchResult, fetch_public_source
from src.international_current.team_name_normalization import normalize_team_name


HISTORICAL_RATING_COLUMNS = [
    "snapshot_date",
    "team_name",
    "normalized_team_name",
    "rating",
    "rating_source",
    "rating_source_url",
    "source_status",
    "is_historical_snapshot",
    "snapshot_confidence",
    "warning",
]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=HISTORICAL_RATING_COLUMNS)


def _normalize_frame(frame: pd.DataFrame, *, source_status: str = "cache_hit") -> pd.DataFrame:
    if frame.empty:
        return _empty()
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        snapshot_date = str(row.get("snapshot_date") or row.get("rating_date") or row.get("date") or "")[:10]
        team = str(row.get("team_name") or row.get("team") or row.get("country") or row.get("normalized_team_name") or "").strip()
        normalized = str(row.get("normalized_team_name") or "").strip()
        if not normalized:
            normalized = normalize_team_name(team).normalized_name
        rating = pd.to_numeric(row.get("rating") or row.get("rating_value") or row.get("elo"), errors="coerce")
        if not snapshot_date or not normalized or pd.isna(rating):
            continue
        historical = str(row.get("is_historical_snapshot", "true")).strip().lower() not in {"false", "0", "no"}
        rows.append({
            "snapshot_date": snapshot_date,
            "team_name": team or normalized,
            "normalized_team_name": normalized,
            "rating": float(rating),
            "rating_source": row.get("rating_source") or row.get("source_name") or "local_historical_rating_snapshot",
            "rating_source_url": row.get("rating_source_url") or row.get("source_url") or "",
            "source_status": row.get("source_status") or source_status,
            "is_historical_snapshot": bool(historical),
            "snapshot_confidence": row.get("snapshot_confidence") or row.get("confidence") or "local_cache",
            "warning": row.get("warning") or "Historical rating snapshot loaded from local/public dated source.",
        })
    return pd.DataFrame(rows, columns=HISTORICAL_RATING_COLUMNS)


def load_historical_rating_snapshots(cache_dir: str | Path = "data/source_cache/current_international") -> pd.DataFrame:
    root = Path(cache_dir)
    parsed = root / "parsed" / "historical_rating_snapshots.csv"
    frames: list[pd.DataFrame] = []
    if parsed.exists():
        frames.append(_normalize_frame(pd.read_csv(parsed), source_status="parsed_cache_hit"))
    local_dir = root / "historical_ratings"
    if local_dir.exists():
        for path in sorted(local_dir.glob("*.csv")):
            frames.append(_normalize_frame(pd.read_csv(path), source_status="local_snapshot_cache_hit"))
    if not frames:
        return _empty()
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(["snapshot_date", "normalized_team_name", "rating_source"], keep="first")
    return out.sort_values(["snapshot_date", "normalized_team_name"]).reset_index(drop=True)


def _snapshot_dates(start_date: str, end_date: str, max_snapshots: int | None) -> list[str]:
    start = pd.to_datetime(start_date, errors="coerce")
    end = pd.to_datetime(end_date, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        end = pd.Timestamp(date.today())
        start = end
    dates = [start.date().isoformat()]
    for year in range(start.year + 1, end.year + 1):
        dates.append(date(year, 1, 1).isoformat())
    if end.date().isoformat() not in dates:
        dates.append(end.date().isoformat())
    dates = sorted(set(dates))
    return dates[:max_snapshots] if max_snapshots else dates


def seed_historical_rating_snapshots(
    *,
    start_date: str,
    end_date: str,
    allow_network: bool = False,
    force_refresh: bool = False,
    max_snapshots: int | None = None,
    cache_dir: str | Path = "data/source_cache/current_international",
) -> dict[str, Any]:
    root = Path(cache_dir)
    parsed_path = root / "parsed" / "historical_rating_snapshots.csv"
    fetches: list[FetchResult] = []
    frames: list[pd.DataFrame] = []
    if parsed_path.exists() and not force_refresh:
        frame = load_historical_rating_snapshots(root)
        return {"snapshots": frame, "fetches": fetches, "parsed_path": parsed_path, "source_status_counts": {"parsed_cache_hit": len(frame)}}

    if not force_refresh:
        frames.append(load_historical_rating_snapshots(root))
    for snapshot_date in _snapshot_dates(start_date, end_date, max_snapshots):
        year, month, day = snapshot_date.split("-")
        url = f"https://www.international-football.net/elo-ratings-table?year={year}&month={month}&day={day}"
        fetch, text = fetch_public_source(
            source_name="international_football_historical_elo",
            source_url=url,
            raw_dir=root / "historical_ratings" / "raw",
            allow_network=allow_network,
        )
        fetches.append(fetch)
        if text:
            parsed = parse_international_football_ratings(text, source_url=url)
            if not parsed.empty:
                parsed["snapshot_date"] = snapshot_date
                parsed["is_historical_snapshot"] = True
                parsed["snapshot_confidence"] = parsed.get("confidence", "dated_public_page")
                parsed["source_status"] = fetch.status
                frames.append(_normalize_frame(parsed, source_status=fetch.status))

    out = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True) if any(not frame.empty for frame in frames) else _empty()
    if not out.empty:
        out = out.drop_duplicates(["snapshot_date", "normalized_team_name", "rating_source"], keep="first")
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    if force_refresh and parsed_path.exists():
        parsed_path.unlink()
    out.to_csv(parsed_path, index=False)
    return {
        "snapshots": out,
        "fetches": fetches,
        "parsed_path": parsed_path,
        "source_status_counts": dict(pd.Series([fetch.status for fetch in fetches]).value_counts()) if fetches else {},
    }
