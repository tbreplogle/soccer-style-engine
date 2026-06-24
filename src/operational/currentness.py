from __future__ import annotations

from pathlib import Path
from typing import Any
import warnings

import pandas as pd
from pandas.errors import PerformanceWarning

from src.operational.season_sanity import check_season_sanity


EXPECTED_RAW_COLUMNS = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
EXPECTED_PROCESSED_COLUMNS = {"date", "league", "home_team", "away_team", "home_goals", "away_goals"}
ODDS_COLUMNS = {"B365H", "B365D", "B365A", "home_odds_close", "draw_odds_close", "away_odds_close"}


def _split(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _read_raw(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    date_values = frame.get("Date")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PerformanceWarning)
        frame = frame.assign(
            _source_file=str(path),
            _source_mtime=path.stat().st_mtime,
            date=pd.to_datetime(date_values, errors="coerce", format="%d/%m/%y"),
        )
        if frame["date"].isna().all():
            frame["date"] = pd.to_datetime(date_values, errors="coerce", dayfirst=True)
    return frame


def _read_processed(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame.get("date"), errors="coerce")
    return frame


def check_data_currentness(
    raw_dir: str | Path = "data/raw/football-data",
    processed: str | Path | None = "data/processed/multi_league_current_match_results.csv",
    as_of_date: str | None = None,
    season_code: str = "2526",
    leagues: str | list[str] = "E0,E1,SP1,D1,I1,F1",
    historical_mode: bool = False,
) -> dict[str, Any]:
    as_of = pd.to_datetime(as_of_date, errors="coerce") if as_of_date else pd.Timestamp.today().normalize()
    checked = _split(leagues)
    raw_root = Path(raw_dir)
    warnings: list[str] = []
    missing_columns: dict[str, list[str]] = {}
    latest_by_league: dict[str, str | None] = {}
    latest_completed_by_league: dict[str, str | None] = {}
    future_counts: dict[str, int] = {}
    completed_counts: dict[str, int] = {}
    odds_by_league: dict[str, bool] = {}
    leagues_missing: list[str] = []
    leagues_stale: list[str] = []

    if pd.isna(as_of):
        return _payload("unsafe", None, None, None, checked, checked, checked, {"as_of_date": ["parse_failed"]}, 0, 0, False, ["as_of_date could not be parsed."], "Fix as_of_date before running.", {}, {})
    raw_frames: list[pd.DataFrame] = []
    for league in checked:
        path = raw_root / f"{league}_{season_code}.csv"
        if not path.exists():
            leagues_missing.append(league)
            continue
        frame = _read_raw(path)
        missing = sorted(EXPECTED_RAW_COLUMNS - set(frame.columns))
        if missing:
            missing_columns[league] = missing
        latest = frame["date"].max()
        latest_by_league[league] = latest.date().isoformat() if pd.notna(latest) else None
        goals_present = pd.to_numeric(frame.get("FTHG"), errors="coerce").notna() & pd.to_numeric(frame.get("FTAG"), errors="coerce").notna()
        completed = frame[goals_present]
        latest_completed = completed["date"].max() if not completed.empty else pd.NaT
        latest_completed_by_league[league] = latest_completed.date().isoformat() if pd.notna(latest_completed) else None
        future_counts[league] = int((frame["date"].notna() & (frame["date"] >= as_of) & ~goals_present).sum())
        completed_counts[league] = int(len(completed))
        odds_by_league[league] = bool(ODDS_COLUMNS.intersection(frame.columns))
        if pd.notna(latest_completed):
            days = int((as_of.normalize() - latest_completed.normalize()).days)
            if days > 14 and as_of <= pd.Timestamp(f"20{season_code[2:]}-06-30"):
                leagues_stale.append(league)
        raw_frames.append(frame)

    processed_path = Path(processed) if processed else None
    processed_state = "not_checked"
    processed_mtime = None
    raw_mtime = max([float(f["_source_mtime"].max()) for f in raw_frames], default=None)
    if processed_path:
        if not processed_path.exists():
            processed_state = "missing"
            if raw_frames:
                warnings.append("Processed data is missing but raw data exists; normalize before relying on the slate.")
        else:
            processed_mtime = processed_path.stat().st_mtime
            processed_state = "newer_than_raw" if raw_mtime is None or processed_mtime >= raw_mtime else "older_than_raw"
            if processed_state == "older_than_raw":
                warnings.append("Processed data is older than raw data; rerun normalization.")
            try:
                processed_frame = _read_processed(processed_path)
                missing = sorted(EXPECTED_PROCESSED_COLUMNS - set(processed_frame.columns))
                if missing:
                    missing_columns["processed"] = missing
            except Exception as exc:
                processed_state = "unreadable"
                warnings.append(f"Processed data could not be read: {exc}")

    latest_completed_values = [pd.to_datetime(v) for v in latest_completed_by_league.values() if v]
    latest_values = [pd.to_datetime(v) for v in latest_by_league.values() if v]
    latest_completed = max(latest_completed_values) if latest_completed_values else pd.NaT
    latest = max(latest_values) if latest_values else pd.NaT
    days_since = int((as_of.normalize() - latest_completed.normalize()).days) if pd.notna(latest_completed) else None
    future_total = sum(future_counts.values())
    completed_total = sum(completed_counts.values())
    odds_available = any(odds_by_league.values())

    season = check_season_sanity(season_code, as_of.date().isoformat(), historical_mode=historical_mode)
    warnings.extend(season["warnings"])
    status = "current"
    action = "Slate is safe to run with current data."
    if leagues_missing and len(leagues_missing) == len(checked):
        status = "missing"
        action = "Download raw Football-Data files before running the slate."
    elif leagues_missing:
        status = "missing"
        action = "Download missing league files or run a reduced-league slate intentionally."
    elif completed_total == 0:
        status = "unsafe"
        action = "Do not run; no completed matches are available."
    elif missing_columns:
        status = "unsafe"
        action = "Fix missing required columns before running."
    elif leagues_stale:
        season_end = pd.to_datetime(season["expected_date_range"]["end"]) if season["expected_date_range"] else pd.NaT
        if pd.notna(season_end) and as_of > season_end:
            status = "probably_current"
            warnings.append("Latest completed match is old, but as_of_date is after season end; treating as offseason/historical context.")
            action = "Proceed as historical/offseason context if intentional."
        else:
            status = "stale"
            action = "Refresh raw data before running or use warn policy only for historical validation."
    elif processed_state in {"missing", "older_than_raw", "unreadable"}:
        status = "probably_current"
        action = "Normalize raw data before treating the run as fully current."
    elif future_total == 0:
        status = "probably_current"
        warnings.append("No future fixtures with missing scores found; this may be historical/offseason context.")
        action = "Proceed for historical validation or rerun when fixture rows are available."

    if season["season_sanity_status"] == "unsafe":
        status = "unsafe"
        action = "Fix season/date sanity before running."

    return _payload(
        status,
        latest.date().isoformat() if pd.notna(latest) else None,
        latest_completed.date().isoformat() if pd.notna(latest_completed) else None,
        days_since,
        checked,
        leagues_missing,
        leagues_stale,
        missing_columns,
        future_total,
        completed_total,
        odds_available,
        warnings,
        action,
        latest_by_league,
        latest_completed_by_league,
        processed_state=processed_state,
        season_sanity=season,
    )


def _payload(
    status: str,
    latest: str | None,
    latest_completed: str | None,
    days_since: int | None,
    checked: list[str],
    missing: list[str],
    stale: list[str],
    missing_columns: dict[str, list[str]],
    future_count: int,
    completed_count: int,
    odds_available: bool,
    warnings: list[str],
    action: str,
    latest_by_league: dict[str, str | None],
    latest_completed_by_league: dict[str, str | None],
    processed_state: str = "not_checked",
    season_sanity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "currentness_status": status,
        "latest_match_date": latest,
        "latest_completed_match_date": latest_completed,
        "days_since_latest_completed": days_since,
        "leagues_checked": checked,
        "leagues_missing": missing,
        "leagues_stale": stale,
        "missing_columns": missing_columns,
        "future_fixture_count": future_count,
        "completed_match_count": completed_count,
        "odds_available": odds_available,
        "warnings": warnings,
        "recommended_action": action,
        "latest_match_date_by_league": latest_by_league,
        "latest_completed_match_date_by_league": latest_completed_by_league,
        "processed_data_state": processed_state,
        "slate_safe_to_run": status in {"current", "probably_current", "stale"},
        "season_sanity": season_sanity or {},
    }


def format_currentness(result: dict[str, Any]) -> str:
    lines = [
        f"currentness_status: {result['currentness_status']}",
        f"latest_match_date: {result['latest_match_date']}",
        f"latest_completed_match_date: {result['latest_completed_match_date']}",
        f"days_since_latest_completed: {result['days_since_latest_completed']}",
        f"processed_data_state: {result['processed_data_state']}",
        f"future_fixture_count: {result['future_fixture_count']}",
        f"completed_match_count: {result['completed_match_count']}",
        f"odds_available: {result['odds_available']}",
        f"missing_leagues: {', '.join(result['leagues_missing']) or 'none'}",
        f"stale_leagues: {', '.join(result['leagues_stale']) or 'none'}",
        f"missing_columns: {result['missing_columns'] or 'none'}",
        "latest_completed_by_league:",
    ]
    for league, value in result["latest_completed_match_date_by_league"].items():
        lines.append(f"- {league}: {value}")
    lines.extend(["warnings:"])
    lines.extend([f"- {warning}" for warning in result["warnings"]] or ["- None"])
    lines.append(f"recommended_action: {result['recommended_action']}")
    return "\n".join(lines)
