from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import warnings

import pandas as pd
from pandas.errors import PerformanceWarning

from src.operational.season_sanity import check_season_sanity


EXPECTED_RAW_COLUMNS = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
EXPECTED_PROCESSED_COLUMNS = {"date", "league", "home_team", "away_team", "home_goals", "away_goals"}
ODDS_COLUMNS = {"B365H", "B365D", "B365A", "home_odds_close", "draw_odds_close", "away_odds_close"}
DEFAULT_EXPECTED_MATCH_COUNTS = {
    "E0": (380,),
    "E1": (552,),
    "SP1": (380,),
    "D1": (306,),
    "I1": (380,),
    "F1": (306, 380),
}


def _split(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _iso_from_mtime(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


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


def _processed_freshness(processed_path: Path | None, raw_files: list[Path]) -> dict[str, Any]:
    files = [path for path in raw_files if path.exists()]
    raw_latest = max([path.stat().st_mtime for path in files], default=None)
    if processed_path is None:
        return {
            "processed_freshness_status": "unknown",
            "raw_latest_modified_at": _iso_from_mtime(raw_latest),
            "processed_modified_at": None,
            "files_compared": [str(path) for path in files],
        }
    if not processed_path.exists():
        return {
            "processed_freshness_status": "missing",
            "raw_latest_modified_at": _iso_from_mtime(raw_latest),
            "processed_modified_at": None,
            "files_compared": [str(path) for path in files],
        }
    processed_mtime = processed_path.stat().st_mtime
    status = "fresh" if raw_latest is None or processed_mtime >= raw_latest else "older_than_raw"
    return {
        "processed_freshness_status": status,
        "raw_latest_modified_at": _iso_from_mtime(raw_latest),
        "processed_modified_at": _iso_from_mtime(processed_mtime),
        "files_compared": [str(path) for path in files],
    }


def _league_status(
    league: str,
    frame: pd.DataFrame,
    as_of: pd.Timestamp,
    season_end: pd.Timestamp | None,
    slate_type: str,
    missing_columns: list[str],
    expected_counts: dict[str, tuple[int, ...]],
) -> dict[str, Any]:
    latest = frame["date"].max()
    goals_present = pd.to_numeric(frame.get("FTHG"), errors="coerce").notna() & pd.to_numeric(frame.get("FTAG"), errors="coerce").notna()
    completed = frame[goals_present]
    latest_completed = completed["date"].max() if not completed.empty else pd.NaT
    future_count = int((frame["date"].notna() & (frame["date"] >= as_of) & ~goals_present).sum())
    completed_count = int(len(completed))
    expected = expected_counts.get(league, tuple())
    expected_min = min(expected) if expected else None
    expected_label = "/".join(str(item) for item in expected) if expected else "unknown"
    completion_pct = (completed_count / expected_min) if expected_min else None
    finished = bool(expected and completed_count in expected and future_count == 0)
    odds_available = bool(ODDS_COLUMNS.intersection(frame.columns))
    warnings_out: list[str] = []
    status = "current"
    if missing_columns:
        status = "unsafe"
        warnings_out.append(f"{league} is missing required columns: {', '.join(missing_columns)}")
    elif completed_count == 0:
        status = "unsafe"
        warnings_out.append(f"{league} has no completed matches.")
    elif finished:
        status = "season_completed"
        warnings_out.append(f"{league} appears season-complete, not stale.")
    elif pd.notna(season_end) and as_of > season_end:
        status = "offseason"
        warnings_out.append(f"{league} is being evaluated after season end; treating as offseason/historical context.")
    else:
        days_since = int((as_of.normalize() - latest_completed.normalize()).days) if pd.notna(latest_completed) else None
        active_mode = slate_type in {"auto", "future"}
        if days_since is not None and days_since > 14:
            status = "stale" if active_mode else "probably_current"
            text = f"{league} latest completed match is {days_since} days before as_of_date."
            warnings_out.append(text if active_mode else f"{text} Historical/manual mode allows this as a warning.")
        elif future_count == 0 and slate_type == "historical":
            status = "probably_current"
        else:
            status = "current"
    return {
        "league": league,
        "status": status,
        "latest_match_date": latest.date().isoformat() if pd.notna(latest) else None,
        "latest_completed_match_date": latest_completed.date().isoformat() if pd.notna(latest_completed) else None,
        "days_since_latest_completed": int((as_of.normalize() - latest_completed.normalize()).days) if pd.notna(latest_completed) else None,
        "expected_match_count": expected_label,
        "completed_match_count": completed_count,
        "completion_pct": round(float(completion_pct), 4) if completion_pct is not None else None,
        "finished": finished,
        "future_fixture_count": future_count,
        "odds_available": odds_available,
        "missing_columns": missing_columns,
        "warnings": warnings_out,
    }


def check_data_currentness(
    raw_dir: str | Path = "data/raw/football-data",
    processed: str | Path | None = "data/processed/multi_league_current_match_results.csv",
    as_of_date: str | None = None,
    season_code: str = "2526",
    leagues: str | list[str] = "E0,E1,SP1,D1,I1,F1",
    historical_mode: bool = False,
    slate_type: str = "auto",
    expected_match_counts: dict[str, tuple[int, ...]] | None = None,
) -> dict[str, Any]:
    as_of = pd.to_datetime(as_of_date, errors="coerce") if as_of_date else pd.Timestamp.today().normalize()
    checked = _split(leagues)
    raw_root = Path(raw_dir)
    expected_counts = expected_match_counts or DEFAULT_EXPECTED_MATCH_COUNTS
    if historical_mode:
        slate_type = "historical"
    if pd.isna(as_of):
        return _payload(
            status="unsafe",
            checked=checked,
            league_rows={},
            missing=checked,
            processed_freshness=_processed_freshness(Path(processed) if processed else None, []),
            warnings=["as_of_date could not be parsed."],
            action="Fix as_of_date before running.",
            season_sanity={},
        )
    season = check_season_sanity(season_code, as_of.date().isoformat(), historical_mode=historical_mode or slate_type == "historical")
    season_end = pd.to_datetime(season["expected_date_range"]["end"]) if season.get("expected_date_range") else None
    league_rows: dict[str, dict[str, Any]] = {}
    raw_files: list[Path] = []
    warnings_out: list[str] = list(season["warnings"])
    leagues_missing: list[str] = []
    for league in checked:
        path = raw_root / f"{league}_{season_code}.csv"
        raw_files.append(path)
        if not path.exists():
            leagues_missing.append(league)
            league_rows[league] = {
                "league": league,
                "status": "missing",
                "latest_match_date": None,
                "latest_completed_match_date": None,
                "days_since_latest_completed": None,
                "expected_match_count": "/".join(str(item) for item in expected_counts.get(league, tuple())) or "unknown",
                "completed_match_count": 0,
                "completion_pct": 0.0,
                "finished": False,
                "future_fixture_count": 0,
                "odds_available": False,
                "missing_columns": [],
                "warnings": [f"{league}_{season_code}.csv is missing."],
            }
            continue
        frame = _read_raw(path)
        missing = sorted(EXPECTED_RAW_COLUMNS - set(frame.columns))
        row = _league_status(league, frame, as_of, season_end, slate_type, missing, expected_counts)
        league_rows[league] = row
        warnings_out.extend(row["warnings"])
    processed_path = Path(processed) if processed else None
    processed_freshness = _processed_freshness(processed_path, [path for path in raw_files if path.exists()])
    processed_state = processed_freshness["processed_freshness_status"]
    missing_columns: dict[str, list[str]] = {
        league: row["missing_columns"] for league, row in league_rows.items() if row["missing_columns"]
    }
    if processed_path and processed_path.exists():
        try:
            processed_frame = _read_processed(processed_path)
            missing_processed = sorted(EXPECTED_PROCESSED_COLUMNS - set(processed_frame.columns))
            if missing_processed:
                missing_columns["processed"] = missing_processed
        except Exception as exc:
            processed_state = "unknown"
            warnings_out.append(f"Processed data could not be read: {exc}")
    elif processed_state == "missing" and raw_files:
        warnings_out.append("Processed data is missing but raw data exists; normalize before relying on the slate.")
    if processed_state == "older_than_raw":
        warnings_out.append("Processed data is older than relevant raw data; rerun normalization unless this run normalizes first.")
    statuses = {league: row["status"] for league, row in league_rows.items()}
    if any(status == "unsafe" for status in statuses.values()) or "processed" in missing_columns:
        status = "unsafe"
        action = "Fix unsafe league or processed columns before running."
    elif any(status == "missing" for status in statuses.values()):
        status = "missing"
        action = "Download missing league files or run a reduced-league slate intentionally."
    elif all(status in {"season_completed", "offseason"} for status in statuses.values()):
        status = "season_completed" if any(status == "season_completed" for status in statuses.values()) else "historical_ok"
        action = "Proceed as completed-season or historical validation context."
    elif any(status == "stale" for status in statuses.values()):
        status = "stale"
        action = "Refresh active-league data before current/future projections."
    elif any(status in {"probably_current", "offseason"} for status in statuses.values()) or processed_state in {"missing", "older_than_raw", "unknown"}:
        status = "probably_current"
        action = "Proceed with warnings, or normalize/refresh for a fully current run."
    else:
        status = "current"
        action = "Slate is safe to run with current data."
    if season.get("season_sanity_status") == "unsafe":
        status = "unsafe"
        action = "Fix season/date sanity before running."
    return _payload(
        status=status,
        checked=checked,
        league_rows=league_rows,
        missing=[league for league, row in league_rows.items() if row["status"] == "missing"],
        processed_freshness={**processed_freshness, "processed_freshness_status": processed_state},
        warnings=warnings_out,
        action=action,
        season_sanity=season,
        missing_columns=missing_columns,
    )


def _payload(
    status: str,
    checked: list[str],
    league_rows: dict[str, dict[str, Any]],
    missing: list[str],
    processed_freshness: dict[str, Any],
    warnings: list[str],
    action: str,
    season_sanity: dict[str, Any],
    missing_columns: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    missing_columns = missing_columns or {}
    latest_completed_values = [pd.to_datetime(row["latest_completed_match_date"]) for row in league_rows.values() if row.get("latest_completed_match_date")]
    latest_values = [pd.to_datetime(row["latest_match_date"]) for row in league_rows.values() if row.get("latest_match_date")]
    latest_completed = max(latest_completed_values) if latest_completed_values else pd.NaT
    latest = max(latest_values) if latest_values else pd.NaT
    future_total = sum(int(row.get("future_fixture_count") or 0) for row in league_rows.values())
    completed_total = sum(int(row.get("completed_match_count") or 0) for row in league_rows.values())
    odds_available = any(bool(row.get("odds_available")) for row in league_rows.values())
    statuses = {league: row["status"] for league, row in league_rows.items()}
    days_since = max([row["days_since_latest_completed"] for row in league_rows.values() if row.get("days_since_latest_completed") is not None], default=None)
    payload = {
        "overall_currentness_status": status,
        "currentness_status": status,
        "league_statuses": statuses,
        "latest_match_date": latest.date().isoformat() if pd.notna(latest) else None,
        "latest_completed_match_date": latest_completed.date().isoformat() if pd.notna(latest_completed) else None,
        "days_since_latest_completed": days_since,
        "leagues_checked": checked,
        "leagues_missing": missing,
        "leagues_stale": [league for league, row in league_rows.items() if row["status"] == "stale"],
        "leagues_completed": [league for league, row in league_rows.items() if row["status"] == "season_completed"],
        "leagues_unsafe": [league for league, row in league_rows.items() if row["status"] == "unsafe"],
        "league_latest_completed_dates": {league: row.get("latest_completed_match_date") for league, row in league_rows.items()},
        "league_expected_match_counts": {league: row.get("expected_match_count") for league, row in league_rows.items()},
        "league_completed_match_counts": {league: row.get("completed_match_count") for league, row in league_rows.items()},
        "league_completion_pct": {league: row.get("completion_pct") for league, row in league_rows.items()},
        "league_finished_flags": {league: row.get("finished") for league, row in league_rows.items()},
        "missing_columns": missing_columns,
        "future_fixture_count": future_total,
        "completed_match_count": completed_total,
        "odds_available": odds_available,
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_action": action,
        "latest_match_date_by_league": {league: row.get("latest_match_date") for league, row in league_rows.items()},
        "latest_completed_match_date_by_league": {league: row.get("latest_completed_match_date") for league, row in league_rows.items()},
        "processed_data_state": processed_freshness["processed_freshness_status"],
        "processed_freshness_status": processed_freshness["processed_freshness_status"],
        "raw_latest_modified_at": processed_freshness.get("raw_latest_modified_at"),
        "processed_modified_at": processed_freshness.get("processed_modified_at"),
        "files_compared": processed_freshness.get("files_compared", []),
        "slate_safe_to_run": status in {"current", "probably_current", "season_completed", "historical_ok", "offseason", "stale"},
        "season_sanity": season_sanity or {},
    }
    return payload


def format_currentness(result: dict[str, Any]) -> str:
    lines = [
        f"overall_currentness_status: {result['overall_currentness_status']}",
        f"latest_completed_match_date: {result['latest_completed_match_date']}",
        f"processed_freshness_status: {result['processed_freshness_status']}",
        f"raw_latest_modified_at: {result['raw_latest_modified_at']}",
        f"processed_modified_at: {result['processed_modified_at']}",
        f"completed_match_count: {result['completed_match_count']}",
        f"future_fixture_count: {result['future_fixture_count']}",
        f"missing_leagues: {', '.join(result['leagues_missing']) or 'none'}",
        f"stale_leagues: {', '.join(result['leagues_stale']) or 'none'}",
        f"completed_leagues: {', '.join(result['leagues_completed']) or 'none'}",
        "league_statuses:",
        "| league | status | completed | expected | pct | latest_completed | finished |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for league in result["leagues_checked"]:
        lines.append(
            "| "
            + " | ".join([
                league,
                str(result["league_statuses"].get(league)),
                str(result["league_completed_match_counts"].get(league)),
                str(result["league_expected_match_counts"].get(league)),
                str(result["league_completion_pct"].get(league)),
                str(result["league_latest_completed_dates"].get(league)),
                str(result["league_finished_flags"].get(league)),
            ])
            + " |"
        )
    lines.extend(["warnings:"])
    lines.extend([f"- {warning}" for warning in result["warnings"]] or ["- None"])
    lines.append(f"recommended_action: {result['recommended_action']}")
    return "\n".join(lines)


def explain_currentness() -> str:
    return "\n".join([
        "Currentness Status Guide",
        "",
        "- current: league files are present, recent enough, and structurally safe.",
        "- probably_current: usable with caveats, usually historical/manual mode or processed freshness warnings.",
        "- season_completed: expected completed match count is present and no future fixtures remain.",
        "- offseason: the run date is after season end; use as historical context.",
        "- stale: an active current/future league has not updated recently enough.",
        "- missing: required raw league files are absent.",
        "- unsafe: no completed matches, bad date structure, or required columns missing.",
        "",
        "Completed leagues are not stale simply because their final match was earlier than another league's final match.",
        "Historical validation and manual matchup modes warn more gently than current/future slate modes.",
        "Processed freshness compares only the raw CSVs relevant to the run. If processed data is older than those raw files, rerun normalization or let the daily pipeline normalize during the run.",
        "When warnings appear, use the recommended action in the currentness output and inspect run_summary.md before trusting a slate.",
        "This is an operational safety check, not a betting signal.",
    ])
