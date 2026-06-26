from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.reports.slate_report import build_club_slate_report
from src.viewer.static_viewer import build_static_viewer


EXPECTED_LEAGUES = ["E0", "E1", "SP1", "D1", "I1", "F1"]
READY_STATUSES = {
    "ready",
    "ready_with_warnings",
    "blocked_missing_current_fixtures",
    "blocked_missing_historical_data",
    "blocked_missing_calibration",
    "blocked_schema_error",
    "blocked_insufficient_rows",
}


def check_league_readiness(
    *,
    as_of_date: str,
    season: str | None = None,
    leagues: list[str] | None = None,
    require_calibration: bool = False,
    require_current_fixtures: bool = False,
    build_viewer: bool = False,
    max_matches: int = 20,
    output_dir: str | Path = "outputs/club",
    current_input: str | Path = "data/processed/multi_league_current_match_results.csv",
    historical_input: str | Path = "data/processed/multi_season_match_results.csv",
    calibration_root: str | Path = "outputs/calibration",
    viewer_output_dir: str | Path = "outputs/viewer",
) -> dict[str, Any]:
    selected_leagues = leagues or EXPECTED_LEAGUES
    run_dir = Path(output_dir) / as_of_date / "league_readiness"
    run_dir.mkdir(parents=True, exist_ok=True)
    current = _read_match_data(current_input)
    historical = _read_match_data(historical_input)
    inventory = _inventory(current, historical, current_input, historical_input)
    calibration = _latest_club_calibration(calibration_root, as_of_date)
    by_league = _by_league_status(
        current,
        historical,
        selected_leagues,
        as_of_date=as_of_date,
        season=season,
        calibration=calibration,
        require_calibration=require_calibration,
        require_current_fixtures=require_current_fixtures,
    )
    projection_readiness = _projection_readiness(current, selected_leagues, as_of_date)
    calibration_readiness = _calibration_readiness(selected_leagues, calibration)
    status = _overall_status(by_league, historical, current, require_calibration=require_calibration, require_current_fixtures=require_current_fixtures)
    slate_result: dict[str, Any] = {"status": "not_attempted", "reason": ""}
    if not current.empty and bool(projection_readiness["future_fixtures_found"].any()):
        try:
            slate = build_club_slate_report(
                current_input,
                as_of_date,
                projection_profiles=["score_projection"],
                output_dir=run_dir,
                projection_output_dir=run_dir,
                slate_type="future",
                max_matches=max_matches,
            )
            slate_result = {
                "status": "generated" if len(slate["results"]) else "empty",
                "rows": int(len(slate["results"])),
                "csv_path": str(slate["csv_path"]),
                "markdown_path": str(slate["markdown_path"]),
            }
        except Exception as exc:
            slate_result = {"status": "failed", "reason": str(exc)}
    else:
        slate_result = {"status": "not_attempted", "reason": "No future fixtures found; no fake fixtures created."}
    paths = {
        "league_readiness_summary": run_dir / "league_readiness_summary.md",
        "league_readiness_by_league": run_dir / "league_readiness_by_league.csv",
        "club_data_inventory": run_dir / "club_data_inventory.csv",
        "club_projection_readiness": run_dir / "club_projection_readiness.csv",
        "club_calibration_readiness": run_dir / "club_calibration_readiness.csv",
        "manifest": run_dir / "league_readiness_manifest.json",
    }
    by_league.to_csv(paths["league_readiness_by_league"], index=False)
    inventory.to_csv(paths["club_data_inventory"], index=False)
    projection_readiness.to_csv(paths["club_projection_readiness"], index=False)
    calibration_readiness.to_csv(paths["club_calibration_readiness"], index=False)
    manifest = {
        "entry_type": "club_league_readiness",
        "run_id": f"club_league_readiness_{as_of_date}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of_date,
        "season": season or "",
        "leagues": selected_leagues,
        "status": status,
        "require_calibration": require_calibration,
        "require_current_fixtures": require_current_fixtures,
        "current_statsbomb_live_data_used": False,
        "proxy_adjustments_enabled": False,
        "betting_recommendations": False,
        "slate_generation": slate_result,
        "calibration": calibration,
        "output_paths": {key: str(path) for key, path in paths.items()},
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    paths["league_readiness_summary"].write_text(_summary_markdown(manifest, by_league, inventory), encoding="utf-8")
    viewer: dict[str, Any] = {}
    if build_viewer:
        viewer = build_static_viewer(Path(output_dir).parent, viewer_output_dir)
    return {
        "status": status,
        "run_dir": run_dir,
        "paths": {key: str(path) for key, path in paths.items()},
        "by_league": by_league,
        "inventory": inventory,
        "projection_readiness": projection_readiness,
        "calibration_readiness": calibration_readiness,
        "manifest": manifest,
        "viewer": viewer,
    }


def _read_match_data(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    data = pd.read_csv(p)
    if "date" in data:
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
    return data


def _inventory(current: pd.DataFrame, historical: pd.DataFrame, current_path: str | Path, historical_path: str | Path) -> pd.DataFrame:
    rows = []
    for label, path, data in [("current", current_path, current), ("historical", historical_path, historical)]:
        rows.append({
            "dataset": label,
            "path": str(path),
            "exists": Path(path).exists(),
            "rows": int(len(data)),
            "leagues": ", ".join(sorted(data["league"].dropna().astype(str).unique())) if not data.empty and "league" in data else "",
            "seasons": ", ".join(sorted(data["season"].dropna().astype(str).unique())) if not data.empty and "season" in data else "",
            "teams": int(len(set(data.get("home_team", pd.Series(dtype=str)).dropna().astype(str)).union(set(data.get("away_team", pd.Series(dtype=str)).dropna().astype(str))))) if not data.empty else 0,
            "date_min": data["date"].min().date().isoformat() if not data.empty and "date" in data and data["date"].notna().any() else "",
            "date_max": data["date"].max().date().isoformat() if not data.empty and "date" in data and data["date"].notna().any() else "",
            "required_columns_missing": ", ".join([column for column in ["date", "league", "home_team", "away_team", "home_goals", "away_goals"] if column not in data.columns]),
        })
    return pd.DataFrame(rows)


def _by_league_status(
    current: pd.DataFrame,
    historical: pd.DataFrame,
    leagues: list[str],
    *,
    as_of_date: str,
    season: str | None,
    calibration: dict[str, Any],
    require_calibration: bool,
    require_current_fixtures: bool,
) -> pd.DataFrame:
    cutoff = pd.to_datetime(as_of_date)
    rows = []
    calibrated_leagues = set(calibration.get("calibrated_leagues") or [])
    overall_calibration = calibration.get("overall_status") == "valid_calibration"
    for league in leagues:
        cur = current[current["league"].astype(str).eq(league)].copy() if not current.empty and "league" in current else pd.DataFrame()
        hist = historical[historical["league"].astype(str).eq(league)].copy() if not historical.empty and "league" in historical else pd.DataFrame()
        if season and not cur.empty and "season" in cur:
            cur = cur[cur["season"].astype(str).eq(str(season))]
        future = cur[(cur["date"] >= cutoff) & (cur["home_goals"].isna() | cur["away_goals"].isna())] if not cur.empty else pd.DataFrame()
        warnings = []
        status = "ready"
        if hist.empty:
            status = "blocked_missing_historical_data"
        elif require_current_fixtures and future.empty:
            status = "blocked_missing_current_fixtures"
        elif require_calibration and not (league in calibrated_leagues or overall_calibration):
            status = "blocked_missing_calibration"
        elif future.empty:
            status = "ready_with_warnings"
            warnings.append("No future fixtures found; historical/current completed rows are available but no slate is available without manual or downloaded fixtures.")
        elif league not in calibrated_leagues and overall_calibration:
            status = "ready_with_warnings"
            warnings.append("League-specific calibration missing; overall club calibration fallback is available.")
        rows.append({
            "league": league,
            "status": status,
            "current_rows": int(len(cur)),
            "historical_rows": int(len(hist)),
            "teams_current": _team_count(cur),
            "teams_historical": _team_count(hist),
            "future_fixtures": int(len(future)),
            "current_date_min": _date_min(cur),
            "current_date_max": _date_max(cur),
            "historical_date_min": _date_min(hist),
            "historical_date_max": _date_max(hist),
            "calibration_status": calibration.get("overall_status", ""),
            "league_calibration_available": league in calibrated_leagues,
            "warnings": " | ".join(warnings),
        })
    return pd.DataFrame(rows)


def _projection_readiness(current: pd.DataFrame, leagues: list[str], as_of_date: str) -> pd.DataFrame:
    cutoff = pd.to_datetime(as_of_date)
    rows = []
    for league in leagues:
        cur = current[current["league"].astype(str).eq(league)].copy() if not current.empty and "league" in current else pd.DataFrame()
        future = cur[(cur["date"] >= cutoff) & (cur["home_goals"].isna() | cur["away_goals"].isna())] if not cur.empty else pd.DataFrame()
        rows.append({
            "league": league,
            "projected_slate_can_be_generated": bool(len(future)),
            "future_fixtures_found": int(len(future)),
            "poisson_board_can_be_generated": bool(len(future)),
            "reason": "" if len(future) else "No future fixtures in current processed data.",
        })
    return pd.DataFrame(rows)


def _calibration_readiness(leagues: list[str], calibration: dict[str, Any]) -> pd.DataFrame:
    calibrated = set(calibration.get("calibrated_leagues") or [])
    overall = calibration.get("overall_status") == "valid_calibration"
    return pd.DataFrame([
        {
            "league": league,
            "league_calibration_available": league in calibrated,
            "overall_fallback_available": overall,
            "calibration_status": "ready" if league in calibrated or overall else "blocked_missing_calibration",
            "calibration_run_dir": calibration.get("run_dir", ""),
        }
        for league in leagues
    ])


def _latest_club_calibration(calibration_root: str | Path, as_of_date: str) -> dict[str, Any]:
    source_dir = Path(calibration_root) / as_of_date / "club_historical"
    manifests = sorted(source_dir.glob("*/calibration_manifest.json"))
    if not manifests:
        return {"overall_status": "missing", "run_dir": "", "calibrated_leagues": []}
    latest = max(manifests, key=lambda path: json.loads(path.read_text(encoding="utf-8")).get("calibration_created_at", ""))
    manifest = json.loads(latest.read_text(encoding="utf-8"))
    league_path = latest.parent / "league_calibration_summary.csv"
    leagues = []
    if league_path.exists():
        try:
            frame = pd.read_csv(league_path)
            if "league" in frame:
                leagues = frame["league"].dropna().astype(str).tolist()
        except Exception:
            leagues = []
    return {
        "overall_status": manifest.get("calibration_status"),
        "run_dir": str(latest.parent),
        "row_count": (manifest.get("metrics") or {}).get("row_count"),
        "calibrated_leagues": leagues,
    }


def _overall_status(by_league: pd.DataFrame, historical: pd.DataFrame, current: pd.DataFrame, *, require_calibration: bool, require_current_fixtures: bool) -> str:
    if historical.empty:
        return "blocked_missing_historical_data"
    if by_league.empty:
        return "blocked_schema_error"
    statuses = set(by_league["status"].astype(str))
    blocked = [status for status in statuses if status.startswith("blocked")]
    if blocked:
        if "blocked_missing_calibration" in blocked and require_calibration:
            return "blocked_missing_calibration"
        if "blocked_missing_current_fixtures" in blocked and require_current_fixtures:
            return "blocked_missing_current_fixtures"
        if "blocked_missing_historical_data" in blocked:
            return "blocked_missing_historical_data"
        return sorted(blocked)[0]
    if any(status == "ready_with_warnings" for status in statuses):
        return "ready_with_warnings"
    return "ready"


def _team_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    return len(set(frame.get("home_team", pd.Series(dtype=str)).dropna().astype(str)).union(set(frame.get("away_team", pd.Series(dtype=str)).dropna().astype(str))))


def _date_min(frame: pd.DataFrame) -> str:
    return frame["date"].min().date().isoformat() if not frame.empty and "date" in frame and frame["date"].notna().any() else ""


def _date_max(frame: pd.DataFrame) -> str:
    return frame["date"].max().date().isoformat() if not frame.empty and "date" in frame and frame["date"].notna().any() else ""


def _summary_markdown(manifest: dict[str, Any], by_league: pd.DataFrame, inventory: pd.DataFrame) -> str:
    lines = [
        "# Club League Readiness",
        "",
        f"- Status: `{manifest['status']}`",
        f"- As-of date: `{manifest['as_of_date']}`",
        f"- Leagues: `{', '.join(manifest['leagues'])}`",
        f"- Require calibration: `{manifest['require_calibration']}`",
        f"- Require current fixtures: `{manifest['require_current_fixtures']}`",
        "",
        "## Guardrails",
        "",
        "- No fake fixtures or results are created.",
        "- Current StatsBomb live data is not used.",
        "- Proxy/style adjustments remain disabled by default.",
        "- No betting recommendations are produced.",
        "",
        "## By League",
        "",
        _markdown_table(by_league),
        "",
        "## Data Inventory",
        "",
        _markdown_table(inventory),
    ]
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    columns = list(frame.columns)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(row.get(column, "")).replace("|", "\\|") for column in columns) + " |")
    return "\n".join(lines)
