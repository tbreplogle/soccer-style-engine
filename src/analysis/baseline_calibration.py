from __future__ import annotations

import json
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.analysis.baseline_tuning import (
    default_rating_baseline_parameters,
    project_rows_with_candidate,
    write_baseline_tuning_outputs,
)
from src.analysis.scoreline_calibration import write_scoreline_diagnostics
from src.data_ingestion.multi_league_football_data import normalize_multi_season_football_data
from src.models.score_projection import _projection_from_xg
from src.international_current.current_international_schema import CurrentInternationalFixture, CurrentInternationalTeamRating
from src.international_current.historical_rating_matcher import attach_historical_ratings
from src.international_current.historical_rating_snapshots import load_historical_rating_snapshots
from src.international_current.historical_results import load_historical_results
from src.international_current.rating_projection import project_from_fixture_and_ratings


CALIBRATION_STATUSES = {
    "valid_calibration",
    "diagnostic_only",
    "diagnostic_only_current_rating_leakage",
    "blocked_missing_historical_ratings",
    "blocked_missing_results",
    "blocked_insufficient_rows",
}

CLUB_REQUIRED_COLUMNS = ["date", "home_team", "away_team", "home_goals", "away_goals"]
CLUB_HISTORICAL_PATHS = [
    Path("data/processed/multi_season_match_results.csv"),
    Path("data/processed/multi_league_current_match_results.csv"),
    Path("data/processed/current_match_results.csv"),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id(data_source: str, created_at: str) -> str:
    timestamp = created_at[:19].replace("-", "").replace("T", "_").replace(":", "")
    suffix = hashlib.sha1(created_at.encode("utf-8")).hexdigest()[:8]
    return f"cal_{data_source}_{timestamp}_{suffix}"


def _config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _calibration_run_context(
    *,
    as_of_date: str,
    data_source: str,
    output_dir: str | Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    created_at = _now_iso()
    run_id = _run_id(data_source, created_at)
    config_hash = _config_hash(config)
    run_dir = Path(output_dir) / as_of_date / data_source / run_id
    return {
        "created_at": created_at,
        "run_id": run_id,
        "config_hash": config_hash,
        "run_dir": run_dir,
        "date_dir": Path(output_dir) / as_of_date,
        "source_dir": Path(output_dir) / as_of_date / data_source,
    }


def _latest_manifest_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "calibration_run_id": manifest.get("calibration_run_id"),
        "run_id": manifest.get("run_id"),
        "run_date": manifest.get("run_date"),
        "generated_at": manifest.get("generated_at"),
        "calibration_created_at": manifest.get("calibration_created_at"),
        "calibration_data_source": manifest.get("calibration_data_source"),
        "calibration_output_dir": manifest.get("calibration_output_dir"),
        "calibration_status": manifest.get("calibration_status"),
        "metrics": manifest.get("metrics") or {},
        "recommendations": manifest.get("recommendations") or [],
        "manifest_path": manifest.get("output_paths", {}).get("manifest"),
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if np.isnan(number):
        return default
    return number


def _result_label(home_goals: float, away_goals: float) -> str:
    if home_goals > away_goals:
        return "home"
    if away_goals > home_goals:
        return "away"
    return "draw"


def _log_loss(row: pd.Series) -> float:
    actual = _result_label(row["home_goals"], row["away_goals"])
    prob = row["home_win_prob"] if actual == "home" else row["away_win_prob"] if actual == "away" else row["draw_prob"]
    return float(-np.log(max(1e-9, float(prob))))


def _brier(row: pd.Series) -> float:
    actual = np.array([
        row["home_goals"] > row["away_goals"],
        row["home_goals"] == row["away_goals"],
        row["home_goals"] < row["away_goals"],
    ], dtype=float)
    pred = np.array([row["home_win_prob"], row["draw_prob"], row["away_win_prob"]], dtype=float)
    return float(np.mean((pred - actual) ** 2))


def _bucket(value: float) -> str:
    start = min(0.9, max(0.0, np.floor(value * 10.0) / 10.0))
    end = start + 0.1
    return f"{start:.1f}-{end:.1f}"


def probability_bucket_calibration(rows: pd.DataFrame) -> pd.DataFrame:
    bucket_rows: list[dict[str, Any]] = []
    for label, prob_col, actual_fn in [
        ("home_win", "home_win_prob", lambda r: r["home_goals"] > r["away_goals"]),
        ("draw", "draw_prob", lambda r: r["home_goals"] == r["away_goals"]),
        ("away_win", "away_win_prob", lambda r: r["home_goals"] < r["away_goals"]),
    ]:
        if rows.empty or prob_col not in rows:
            continue
        work = rows.copy()
        work["bucket"] = work[prob_col].astype(float).apply(_bucket)
        work["actual"] = work.apply(actual_fn, axis=1).astype(float)
        grouped = work.groupby("bucket", observed=False)
        for bucket, group in grouped:
            bucket_rows.append({
                "market": label,
                "probability_bucket": bucket,
                "rows": int(len(group)),
                "average_probability": float(group[prob_col].mean()),
                "actual_rate": float(group["actual"].mean()),
                "calibration_gap": float(group[prob_col].mean() - group["actual"].mean()),
            })
    return pd.DataFrame(bucket_rows)


def totals_bucket_calibration(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty or "over_2_5_prob" not in rows:
        return pd.DataFrame(columns=["probability_bucket", "rows", "average_probability", "actual_rate", "calibration_gap"])
    work = rows.copy()
    work["bucket"] = work["over_2_5_prob"].astype(float).apply(_bucket)
    work["actual_over_2_5"] = ((work["home_goals"] + work["away_goals"]) > 2.5).astype(float)
    out = []
    for bucket, group in work.groupby("bucket", observed=False):
        out.append({
            "probability_bucket": bucket,
            "rows": int(len(group)),
            "average_probability": float(group["over_2_5_prob"].mean()),
            "actual_rate": float(group["actual_over_2_5"].mean()),
            "calibration_gap": float(group["over_2_5_prob"].mean() - group["actual_over_2_5"].mean()),
        })
    return pd.DataFrame(out)


def evaluate_projection_calibration(rows: pd.DataFrame, *, status: str = "valid_calibration", data_source: str = "synthetic") -> dict[str, Any]:
    if status not in CALIBRATION_STATUSES:
        raise ValueError(f"Unsupported calibration status: {status}")
    data = rows.copy()
    if data.empty:
        metrics = _empty_metrics(status, data_source, 0)
        return {
            "status": status,
            "metrics": metrics,
            "wdl_calibration": pd.DataFrame(),
            "totals_calibration": pd.DataFrame(),
            "probability_buckets": pd.DataFrame(),
            "scoreline_calibration": pd.DataFrame(),
            "recommendations": ["insufficient_data"],
            "rows": data,
        }
    for column in ["home_goals", "away_goals", "home_xg", "away_xg", "home_win_prob", "draw_prob", "away_win_prob"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["home_goals", "away_goals", "home_xg", "away_xg", "home_win_prob", "draw_prob", "away_win_prob"]).copy()
    if "over_2_5_prob" not in data:
        data["over_2_5_prob"] = np.nan
    data["over_2_5_prob"] = pd.to_numeric(data["over_2_5_prob"], errors="coerce").fillna(0.5)
    data["projected_total"] = data["home_xg"] + data["away_xg"]
    data["actual_total"] = data["home_goals"] + data["away_goals"]
    data["actual_result"] = data.apply(lambda row: _result_label(row["home_goals"], row["away_goals"]), axis=1)
    data["predicted_result"] = data[["home_win_prob", "draw_prob", "away_win_prob"]].idxmax(axis=1).map({
        "home_win_prob": "home",
        "draw_prob": "draw",
        "away_win_prob": "away",
    })
    data["predicted_over_2_5"] = data["over_2_5_prob"] >= 0.5
    data["actual_over_2_5"] = data["actual_total"] > 2.5
    data["most_likely_score"] = data.get("most_likely_score", "").astype(str) if "most_likely_score" in data else ""
    data["actual_score"] = data["home_goals"].astype(int).astype(str) + "-" + data["away_goals"].astype(int).astype(str)
    data["most_likely_score_clean"] = data["most_likely_score"].str.replace(" ", "", regex=False)
    top3_hit = data.get("top_3_scores", pd.Series([""] * len(data))).astype(str).apply(lambda text: [part.strip().replace(" ", "") for part in text.split("|")])
    top3_hit_rate = float(np.mean([actual in predicted for actual, predicted in zip(data["actual_score"], top3_hit)])) if len(data) else 0.0
    metrics = {
        "calibration_status": status,
        "data_source": data_source,
        "row_count": int(len(data)),
        "leakage_safe": status == "valid_calibration",
        "wdl_log_loss": float(data.apply(_log_loss, axis=1).mean()),
        "brier_score": float(data.apply(_brier, axis=1).mean()),
        "accuracy": float((data["actual_result"] == data["predicted_result"]).mean()),
        "total_goals_mae": float((data["projected_total"] - data["actual_total"]).abs().mean()),
        "home_goals_mae": float((data["home_xg"] - data["home_goals"]).abs().mean()),
        "away_goals_mae": float((data["away_xg"] - data["away_goals"]).abs().mean()),
        "over_under_2_5_brier_score": float(np.mean((data["over_2_5_prob"] - data["actual_over_2_5"].astype(float)) ** 2)),
        "over_under_2_5_accuracy": float((data["predicted_over_2_5"] == data["actual_over_2_5"]).mean()),
        "most_likely_score_hit_rate": float((data["most_likely_score_clean"] == data["actual_score"]).mean()),
        "top_3_correct_score_hit_rate": top3_hit_rate,
        "mean_projected_total": float(data["projected_total"].mean()),
        "mean_actual_total": float(data["actual_total"].mean()),
        "favorite_win_rate": _favorite_win_rate(data),
        "draw_actual_rate": float((data["actual_result"] == "draw").mean()),
        "draw_average_probability": float(data["draw_prob"].mean()),
    }
    probability_buckets = probability_bucket_calibration(data)
    totals_calibration = totals_bucket_calibration(data)
    wdl_calibration = pd.DataFrame([{
        "rows": metrics["row_count"],
        "wdl_log_loss": metrics["wdl_log_loss"],
        "brier_score": metrics["brier_score"],
        "accuracy": metrics["accuracy"],
        "favorite_win_rate": metrics["favorite_win_rate"],
        "draw_average_probability": metrics["draw_average_probability"],
        "draw_actual_rate": metrics["draw_actual_rate"],
    }])
    scoreline_calibration = pd.DataFrame([{
        "rows": metrics["row_count"],
        "most_likely_score_hit_rate": metrics["most_likely_score_hit_rate"],
        "top_3_correct_score_hit_rate": metrics["top_3_correct_score_hit_rate"],
        "home_goals_mae": metrics["home_goals_mae"],
        "away_goals_mae": metrics["away_goals_mae"],
        "total_goals_mae": metrics["total_goals_mae"],
    }])
    return {
        "status": status,
        "metrics": metrics,
        "wdl_calibration": wdl_calibration,
        "totals_calibration": totals_calibration,
        "probability_buckets": probability_buckets,
        "scoreline_calibration": scoreline_calibration,
        "recommendations": calibration_recommendations(metrics, probability_buckets),
        "rows": data,
    }


def _favorite_win_rate(data: pd.DataFrame) -> float:
    favorite = data[["home_win_prob", "away_win_prob"]].idxmax(axis=1)
    wins = []
    for fav, (_, row) in zip(favorite, data.iterrows()):
        wins.append((fav == "home_win_prob" and row["home_goals"] > row["away_goals"]) or (fav == "away_win_prob" and row["away_goals"] > row["home_goals"]))
    return float(np.mean(wins)) if wins else 0.0


def _empty_metrics(status: str, data_source: str, row_count: int) -> dict[str, Any]:
    return {
        "calibration_status": status,
        "data_source": data_source,
        "row_count": row_count,
        "leakage_safe": status == "valid_calibration",
        "wdl_log_loss": None,
        "brier_score": None,
        "accuracy": None,
        "total_goals_mae": None,
        "home_goals_mae": None,
        "away_goals_mae": None,
        "over_under_2_5_brier_score": None,
        "over_under_2_5_accuracy": None,
        "most_likely_score_hit_rate": None,
        "top_3_correct_score_hit_rate": None,
    }


def calibration_recommendations(metrics: dict[str, Any], buckets: pd.DataFrame) -> list[str]:
    recommendations: list[str] = []
    if not metrics.get("row_count"):
        return ["insufficient_data"]
    if metrics.get("calibration_status") == "blocked_missing_historical_ratings":
        recommendations.append("historical_rating_snapshots_needed")
    draw_gap = _safe_float(metrics.get("draw_average_probability")) - _safe_float(metrics.get("draw_actual_rate"))
    if draw_gap > 0.06:
        recommendations.append("draw_probability_high")
    mean_total_gap = _safe_float(metrics.get("mean_projected_total")) - _safe_float(metrics.get("mean_actual_total"))
    if mean_total_gap > 0.15:
        recommendations.append("totals_too_high")
    elif mean_total_gap < -0.15:
        recommendations.append("totals_too_low")
    if not buckets.empty:
        high = buckets[pd.to_numeric(buckets["average_probability"], errors="coerce") >= 0.65]
        if not high.empty and float((high["average_probability"] - high["actual_rate"]).mean()) > 0.08:
            recommendations.append("baseline_overconfident")
        elif not high.empty and float((high["actual_rate"] - high["average_probability"]).mean()) > 0.08:
            recommendations.append("baseline_underconfident")
    if not recommendations:
        recommendations.append("insufficient_data" if int(metrics.get("row_count") or 0) < 100 else "continue_monitoring")
    return list(dict.fromkeys(recommendations))


def _blocked_result(
    status: str,
    *,
    as_of_date: str,
    data_source: str,
    min_rows: int,
    output_dir: str | Path,
    reason: str,
    run_context: dict[str, Any],
    run_tuning: bool = False,
    tuning_profile: str = "small",
    primary_metric: str = "composite",
    save_tuning_candidates: bool = False,
    apply_tuning: bool = False,
    holdout_season: str | None = None,
    holdout_start_date: str | None = None,
    holdout_end_date: str | None = None,
    train_start_date: str | None = None,
    train_end_date: str | None = None,
    club_diagnostics: dict[str, Any] | None = None,
    club_filter_breakdown: pd.DataFrame | None = None,
) -> dict[str, Any]:
    result = evaluate_projection_calibration(pd.DataFrame(), status=status, data_source=data_source)
    if status == "blocked_missing_historical_ratings":
        result["recommendations"] = ["historical_rating_snapshots_needed"]
    result["metrics"]["as_of_date"] = as_of_date
    result["metrics"]["min_rows"] = min_rows
    result["metrics"]["blocked_reason"] = reason
    if club_diagnostics is not None:
        result["club_diagnostics"] = club_diagnostics
    if club_filter_breakdown is not None:
        result["club_filter_breakdown"] = club_filter_breakdown
    return _write_outputs(
        result,
        as_of_date=as_of_date,
        data_source=data_source,
        output_dir=output_dir,
        limitations=[reason],
        run_context=run_context,
        run_tuning=run_tuning,
        tuning_profile=tuning_profile,
        primary_metric=primary_metric,
        save_tuning_candidates=save_tuning_candidates,
        apply_tuning=apply_tuning,
        holdout_season=holdout_season,
        holdout_start_date=holdout_start_date,
        holdout_end_date=holdout_end_date,
        train_start_date=train_start_date,
        train_end_date=train_end_date,
    )


def _international_historical_projection_rows(
    *,
    cache_dir: str | Path = "data/source_cache/current_international",
    max_rows: int | None = None,
    max_snapshot_age_days: int = 365,
) -> tuple[pd.DataFrame, str, str]:
    snapshots = load_historical_rating_snapshots(cache_dir)
    if snapshots.empty:
        return pd.DataFrame(), "blocked_missing_historical_ratings", "Historical international rating snapshots are not available, so leakage-safe current rating baseline calibration is blocked."
    results = load_historical_results(cache_dir)
    if results.empty:
        return pd.DataFrame(), "blocked_missing_results", "No historical international match results were found in the parsed/local cache."
    matched = attach_historical_ratings(results, snapshots, max_snapshot_age_days=max_snapshot_age_days)
    matched = matched[matched["rating_match_status"].eq("both_ratings_matched")].copy()
    if max_rows:
        matched = matched.head(max_rows)
    rows: list[dict[str, Any]] = []
    for _, match in matched.iterrows():
        fixture = CurrentInternationalFixture(
            source_name="historical_international_result",
            match_date=str(match["match_date"]),
            competition=str(match.get("competition", "")),
            home_team=str(match["home_team"]),
            away_team=str(match["away_team"]),
            neutral_site=str(match.get("neutral_site", "true")),
            reliability_status="historical_result_with_snapshot",
        )
        home_rating = CurrentInternationalTeamRating(
            source_name="historical_rating_snapshot",
            team=str(match["home_team"]),
            rating_value=float(match["home_rating"]),
            rating_date=str(match["home_rating_snapshot_date"]),
        )
        away_rating = CurrentInternationalTeamRating(
            source_name="historical_rating_snapshot",
            team=str(match["away_team"]),
            rating_value=float(match["away_rating"]),
            rating_date=str(match["away_rating_snapshot_date"]),
        )
        baseline = project_from_fixture_and_ratings(fixture, home_rating, away_rating)
        probs = _projection_from_xg(float(baseline["projected_home_xg"]), float(baseline["projected_away_xg"]))
        rows.append({
            "date": match["match_date"],
            "home_team": match["home_team"],
            "away_team": match["away_team"],
            "home_goals": float(match["home_goals"]),
            "away_goals": float(match["away_goals"]),
            "home_rating": float(match["home_rating"]),
            "away_rating": float(match["away_rating"]),
            "home_rating_snapshot_date": match["home_rating_snapshot_date"],
            "away_rating_snapshot_date": match["away_rating_snapshot_date"],
            "home_xg": baseline["projected_home_xg"],
            "away_xg": baseline["projected_away_xg"],
            "home_win_prob": baseline["home_win_probability"],
            "draw_prob": baseline["draw_probability"],
            "away_win_prob": baseline["away_win_probability"],
            "over_2_5_prob": probs["over_2_5_prob"],
            "most_likely_score": baseline["most_likely_score"],
        })
    return pd.DataFrame(rows), "valid_calibration", ""


def _inspect_club_path(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "usable": False,
        "rows": 0,
        "required_columns_present": "",
        "required_columns_missing": ", ".join(CLUB_REQUIRED_COLUMNS),
        "leagues_found": "",
        "seasons_found": "",
        "date_min": "",
        "date_max": "",
        "error": "",
    }
    if not path.exists():
        return row
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        row["error"] = str(exc)
        return row
    present = [column for column in CLUB_REQUIRED_COLUMNS if column in frame.columns]
    missing = [column for column in CLUB_REQUIRED_COLUMNS if column not in frame.columns]
    row["rows"] = int(len(frame))
    row["required_columns_present"] = ", ".join(present)
    row["required_columns_missing"] = ", ".join(missing)
    row["usable"] = not missing
    if "league" in frame:
        row["leagues_found"] = ", ".join(map(str, sorted(frame["league"].dropna().astype(str).unique())))
    if "season" in frame:
        row["seasons_found"] = ", ".join(map(str, sorted(frame["season"].dropna().astype(str).unique())))
    if "date" in frame:
        parsed = pd.to_datetime(frame["date"], errors="coerce")
        if parsed.notna().any():
            row["date_min"] = parsed.min().date().isoformat()
            row["date_max"] = parsed.max().date().isoformat()
    return row


def _rebuild_club_historical_from_raw() -> dict[str, Any]:
    raw = Path("data/raw/football-data")
    output = Path("data/processed/multi_season_match_results.csv")
    files = sorted(raw.glob("*.csv")) if raw.exists() else []
    result = {"attempted": False, "status": "not_attempted", "raw_dir": str(raw), "raw_files": len(files), "output_path": str(output), "rows": 0, "error": ""}
    if output.exists() or not files:
        return result
    result["attempted"] = True
    try:
        frame = normalize_multi_season_football_data(raw, output_path=output)
        result["rows"] = int(len(frame))
        result["status"] = "rebuilt" if len(frame) else "rebuilt_empty"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
    return result


def _load_club_historical(max_rows: int | None = None, *, include_diagnostics: bool = False) -> pd.DataFrame | tuple[pd.DataFrame, dict[str, Any]]:
    rebuild = _rebuild_club_historical_from_raw()
    searched = [_inspect_club_path(path) for path in CLUB_HISTORICAL_PATHS]
    selected_path = ""
    selected: pd.DataFrame = pd.DataFrame()
    for row in searched:
        if row["usable"]:
            selected_path = str(row["path"])
            selected = pd.read_csv(selected_path)
            selected["date"] = pd.to_datetime(selected["date"], errors="coerce")
            selected = selected.dropna(subset=["date"]).sort_values("date")
            selected["date"] = selected["date"].dt.date.astype(str)
            break
    diagnostics = {
        "paths_checked": [str(path) for path in CLUB_HISTORICAL_PATHS],
        "path_inventory": searched,
        "selected_path": selected_path,
        "rebuild_from_raw": rebuild,
        "total_raw_rows_found": int(len(selected)),
        "leagues_found": sorted(selected["league"].dropna().astype(str).unique().tolist()) if not selected.empty and "league" in selected else [],
        "seasons_found": sorted(selected["season"].dropna().astype(str).unique().tolist()) if not selected.empty and "season" in selected else [],
        "date_min": selected["date"].min() if not selected.empty and "date" in selected else "",
        "date_max": selected["date"].max() if not selected.empty and "date" in selected else "",
    }
    if max_rows and not selected.empty:
        selected = selected.head(max_rows)
    return (selected, diagnostics) if include_diagnostics else selected


def _diagnostic_projection_rows(matches: pd.DataFrame, min_rows: int) -> pd.DataFrame:
    data = matches.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date", "home_team", "away_team", "home_goals", "away_goals"]).sort_values("date")
    history: dict[str, list[tuple[float, float]]] = {}
    rows = []
    for _, match in data.iterrows():
        home = str(match["home_team"])
        away = str(match["away_team"])
        home_hist = history.get(home, [])
        away_hist = history.get(away, [])
        if len(home_hist) >= 3 and len(away_hist) >= 3:
            league_avg = float(pd.concat([data["home_goals"], data["away_goals"]]).mean()) if not data.empty else 1.25
            home_for = np.mean([item[0] for item in home_hist]) if home_hist else league_avg
            away_against = np.mean([item[1] for item in away_hist]) if away_hist else league_avg
            away_for = np.mean([item[0] for item in away_hist]) if away_hist else league_avg
            home_against = np.mean([item[1] for item in home_hist]) if home_hist else league_avg
            home_xg = max(0.2, 0.58 * home_for + 0.42 * away_against + 0.08)
            away_xg = max(0.2, 0.58 * away_for + 0.42 * home_against - 0.04)
            probs = _projection_from_xg(float(home_xg), float(away_xg))
            rows.append({
                "date": match["date"].date().isoformat(),
                "league": match.get("league", ""),
                "league_name": match.get("league_name", ""),
                "season": match.get("season", ""),
                "season_code": match.get("season_code", ""),
                "home_team": home,
                "away_team": away,
                "home_goals": float(match["home_goals"]),
                "away_goals": float(match["away_goals"]),
                "home_strength_index": float(np.mean([item[0] - item[1] for item in home_hist])) if home_hist else 0.0,
                "away_strength_index": float(np.mean([item[0] - item[1] for item in away_hist])) if away_hist else 0.0,
                "home_xg": float(home_xg),
                "away_xg": float(away_xg),
                "home_win_prob": probs["home_win_prob"],
                "draw_prob": probs["draw_prob"],
                "away_win_prob": probs["away_win_prob"],
                "over_2_5_prob": probs["over_2_5_prob"],
                "most_likely_score": probs["most_likely_score"],
            })
        home_goals = float(match["home_goals"])
        away_goals = float(match["away_goals"])
        history.setdefault(home, []).append((home_goals, away_goals))
        history.setdefault(away, []).append((away_goals, home_goals))
    return pd.DataFrame(rows).head(min_rows) if len(rows) > min_rows else pd.DataFrame(rows)


def _club_filter_breakdown(matches: pd.DataFrame, projected: pd.DataFrame, *, min_rows: int, max_rows: int | None) -> pd.DataFrame:
    if matches.empty:
        return pd.DataFrame([
            {"step": "raw_loaded", "rows": 0, "detail": "No usable club historical file loaded."},
            {"step": "eligible_prior_history", "rows": 0, "detail": f"Requires at least {min_rows} eligible rows."},
        ])
    work = matches.copy()
    required_present = all(column in work.columns for column in CLUB_REQUIRED_COLUMNS)
    work["date"] = pd.to_datetime(work["date"], errors="coerce") if "date" in work else pd.NaT
    goals = work.copy()
    for column in ["home_goals", "away_goals"]:
        if column in goals:
            goals[column] = pd.to_numeric(goals[column], errors="coerce")
    after_required = len(work) if required_present else 0
    after_date = int(work["date"].notna().sum()) if "date" in work else 0
    after_goals = int(goals.dropna(subset=["home_goals", "away_goals"]).shape[0]) if {"home_goals", "away_goals"}.issubset(goals.columns) else 0
    eligible_full = _diagnostic_projection_rows(matches, min_rows=len(matches)) if max_rows else projected
    return pd.DataFrame([
        {"step": "raw_loaded", "rows": int(len(matches)), "detail": "Rows loaded from selected processed club historical file."},
        {"step": "required_columns", "rows": after_required, "detail": "Required columns present." if required_present else "Required columns missing."},
        {"step": "valid_dates", "rows": after_date, "detail": "Rows with parseable match date."},
        {"step": "completed_results", "rows": after_goals, "detail": "Rows with home and away goals."},
        {"step": "eligible_prior_history", "rows": int(len(eligible_full)), "detail": "Rows after each team has at least three prior matches before max_rows."},
        {"step": "max_rows_applied_after_eligibility", "rows": int(len(projected.head(max_rows))) if max_rows else int(len(projected)), "detail": f"max_rows={max_rows}" if max_rows else "No max_rows limit."},
    ])


def _summary_record(metrics: dict[str, Any], recommendation: str) -> dict[str, Any]:
    return {
        "row_count": metrics.get("row_count"),
        "wdl_log_loss": metrics.get("wdl_log_loss"),
        "brier_score": metrics.get("brier_score"),
        "accuracy": metrics.get("accuracy"),
        "total_goals_mae": metrics.get("total_goals_mae"),
        "over_2_5_brier": metrics.get("over_under_2_5_brier_score"),
        "most_likely_score_hit_rate": metrics.get("most_likely_score_hit_rate"),
        "avg_predicted_total": metrics.get("mean_projected_total"),
        "avg_actual_total": metrics.get("mean_actual_total"),
        "recommendation": recommendation,
    }


def _grouped_calibration_outputs(rows: pd.DataFrame, group_cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if rows.empty or not all(column in rows.columns for column in group_cols):
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    summaries: list[dict[str, Any]] = []
    probability: list[pd.DataFrame] = []
    totals: list[pd.DataFrame] = []
    for keys, group in rows.groupby(group_cols, dropna=False):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        key_payload = {column: value for column, value in zip(group_cols, key_values)}
        result = evaluate_projection_calibration(group, data_source="club_historical_group")
        recommendation = "; ".join(result["recommendations"])
        summaries.append({**key_payload, **_summary_record(result["metrics"], recommendation)})
        if not result["probability_buckets"].empty:
            probability.append(pd.concat([pd.DataFrame([key_payload] * len(result["probability_buckets"])).reset_index(drop=True), result["probability_buckets"].reset_index(drop=True)], axis=1))
        if not result["totals_calibration"].empty:
            totals.append(pd.concat([pd.DataFrame([key_payload] * len(result["totals_calibration"])).reset_index(drop=True), result["totals_calibration"].reset_index(drop=True)], axis=1))
    return (
        pd.DataFrame(summaries),
        pd.concat(probability, ignore_index=True) if probability else pd.DataFrame(),
        pd.concat(totals, ignore_index=True) if totals else pd.DataFrame(),
    )


def calibrate_baseline_projections(
    *,
    as_of_date: str | None = None,
    data_source: str = "international_historical",
    min_rows: int = 50,
    allow_diagnostic_leakage: bool = False,
    output_dir: str | Path = "outputs/calibration",
    max_rows: int | None = None,
    cache_dir: str | Path = "data/source_cache/current_international",
    run_tuning: bool = False,
    tuning_profile: str = "small",
    primary_metric: str = "composite",
    save_tuning_candidates: bool = False,
    apply_tuning: bool = False,
    holdout_season: str | None = None,
    holdout_start_date: str | None = None,
    holdout_end_date: str | None = None,
    train_start_date: str | None = None,
    train_end_date: str | None = None,
) -> dict[str, Any]:
    run_date = as_of_date or date.today().isoformat()
    config = {
        "as_of_date": run_date,
        "data_source": data_source,
        "min_rows": min_rows,
        "allow_diagnostic_leakage": allow_diagnostic_leakage,
        "max_rows": max_rows,
        "cache_dir": str(cache_dir),
        "run_tuning": run_tuning,
        "tuning_profile": tuning_profile,
        "primary_metric": primary_metric,
        "save_tuning_candidates": save_tuning_candidates,
        "apply_tuning": apply_tuning,
        "holdout_season": holdout_season,
        "holdout_start_date": holdout_start_date,
        "holdout_end_date": holdout_end_date,
        "train_start_date": train_start_date,
        "train_end_date": train_end_date,
    }
    run_context = _calibration_run_context(as_of_date=run_date, data_source=data_source, output_dir=output_dir, config=config)
    if data_source == "international_historical" and not allow_diagnostic_leakage:
        projected, status, reason = _international_historical_projection_rows(cache_dir=cache_dir, max_rows=max_rows)
        if status != "valid_calibration":
            return _blocked_result(
                status,
                as_of_date=run_date,
                data_source=data_source,
                min_rows=min_rows,
                output_dir=output_dir,
                reason=reason,
                run_context=run_context,
                run_tuning=run_tuning,
                tuning_profile=tuning_profile,
                primary_metric=primary_metric,
                save_tuning_candidates=save_tuning_candidates,
                apply_tuning=apply_tuning,
                holdout_season=holdout_season,
                holdout_start_date=holdout_start_date,
                holdout_end_date=holdout_end_date,
                train_start_date=train_start_date,
                train_end_date=train_end_date,
            )
        if len(projected) < min_rows:
            return _blocked_result(
                "blocked_insufficient_rows",
                as_of_date=run_date,
                data_source=data_source,
                min_rows=min_rows,
                output_dir=output_dir,
                reason=f"Only {len(projected)} leakage-safe historical international rows with matched snapshots were available; min_rows={min_rows}.",
                run_context=run_context,
                run_tuning=run_tuning,
                tuning_profile=tuning_profile,
                primary_metric=primary_metric,
                save_tuning_candidates=save_tuning_candidates,
                apply_tuning=apply_tuning,
                holdout_season=holdout_season,
                holdout_start_date=holdout_start_date,
                holdout_end_date=holdout_end_date,
                train_start_date=train_start_date,
                train_end_date=train_end_date,
            )
        result = evaluate_projection_calibration(projected, status="valid_calibration", data_source=data_source)
        result["metrics"]["as_of_date"] = run_date
        result["metrics"]["min_rows"] = min_rows
        limitations = [
            "International calibration uses only match rows with historical rating snapshots on or before match date.",
            "No style-aware xG inputs are included yet; this measures the rating-only baseline.",
        ]
        return _write_outputs(
            result,
            as_of_date=run_date,
            data_source=data_source,
            output_dir=output_dir,
            limitations=limitations,
            run_context=run_context,
            run_tuning=run_tuning,
            tuning_profile=tuning_profile,
            primary_metric=primary_metric,
            save_tuning_candidates=save_tuning_candidates,
            apply_tuning=apply_tuning,
            holdout_season=holdout_season,
            holdout_start_date=holdout_start_date,
            holdout_end_date=holdout_end_date,
            train_start_date=train_start_date,
            train_end_date=train_end_date,
        )
    if data_source == "current_international_results":
        return _blocked_result(
            "blocked_missing_results",
            as_of_date=run_date,
            data_source=data_source,
            min_rows=min_rows,
            output_dir=output_dir,
            reason="Current international fixture projections do not include completed outcomes for calibration.",
            run_context=run_context,
            run_tuning=run_tuning,
            tuning_profile=tuning_profile,
            primary_metric=primary_metric,
            save_tuning_candidates=save_tuning_candidates,
            apply_tuning=apply_tuning,
            holdout_season=holdout_season,
            holdout_start_date=holdout_start_date,
            holdout_end_date=holdout_end_date,
            train_start_date=train_start_date,
            train_end_date=train_end_date,
        )
    try:
        loaded = _load_club_historical(include_diagnostics=True)
    except TypeError:
        loaded = (_load_club_historical(), {"paths_checked": [str(path) for path in CLUB_HISTORICAL_PATHS], "path_inventory": [], "selected_path": "test_monkeypatch", "total_raw_rows_found": 0})
    matches, club_diagnostics = loaded if isinstance(loaded, tuple) else (loaded, {})
    if matches.empty:
        breakdown = _club_filter_breakdown(matches, pd.DataFrame(), min_rows=min_rows, max_rows=max_rows)
        club_diagnostics["reason_blocked"] = "No usable historical match-result table was found."
        club_diagnostics["suggested_repair"] = "Restore data/processed/multi_season_match_results.csv or rebuild it from existing data/raw/football-data CSVs."
        return _blocked_result(
            "blocked_missing_results",
            as_of_date=run_date,
            data_source=data_source,
            min_rows=min_rows,
            output_dir=output_dir,
            reason="No usable historical match-result table was found.",
            run_context=run_context,
            run_tuning=run_tuning,
            tuning_profile=tuning_profile,
            primary_metric=primary_metric,
            save_tuning_candidates=save_tuning_candidates,
            apply_tuning=apply_tuning,
            holdout_season=holdout_season,
            holdout_start_date=holdout_start_date,
            holdout_end_date=holdout_end_date,
            train_start_date=train_start_date,
            train_end_date=train_end_date,
            club_diagnostics=club_diagnostics,
            club_filter_breakdown=breakdown,
        )
    projected = _diagnostic_projection_rows(matches, min_rows=max_rows or len(matches))
    breakdown = _club_filter_breakdown(matches, projected, min_rows=min_rows, max_rows=max_rows)
    if len(projected) < min_rows:
        club_diagnostics["reason_blocked"] = (
            f"Only {len(projected)} selected eligible historical rows were available after max_rows={max_rows}; min_rows={min_rows}."
            if max_rows
            else f"Only {len(projected)} eligible historical rows were available; min_rows={min_rows}."
        )
        club_diagnostics["suggested_repair"] = "If --max-rows is set, increase or remove it so enough prior-history rows survive eligibility filtering."
        return _blocked_result(
            "blocked_insufficient_rows",
            as_of_date=run_date,
            data_source=data_source,
            min_rows=min_rows,
            output_dir=output_dir,
            reason=f"Only {len(projected)} eligible historical rows were available; min_rows={min_rows}.",
            run_context=run_context,
            run_tuning=run_tuning,
            tuning_profile=tuning_profile,
            primary_metric=primary_metric,
            save_tuning_candidates=save_tuning_candidates,
            apply_tuning=apply_tuning,
            holdout_season=holdout_season,
            holdout_start_date=holdout_start_date,
            holdout_end_date=holdout_end_date,
            train_start_date=train_start_date,
            train_end_date=train_end_date,
            club_diagnostics=club_diagnostics,
            club_filter_breakdown=breakdown,
        )
    status = "diagnostic_only_current_rating_leakage" if allow_diagnostic_leakage and data_source == "international_historical" else "valid_calibration"
    if data_source == "club_historical":
        status = "valid_calibration"
    result = evaluate_projection_calibration(projected.head(max_rows) if max_rows else projected, status=status, data_source=data_source)
    if data_source == "club_historical":
        club_diagnostics["reason_blocked"] = ""
        club_diagnostics["suggested_repair"] = "No repair needed; club historical calibration has enough eligible rows."
        result["club_diagnostics"] = club_diagnostics
        result["club_filter_breakdown"] = breakdown
    result["metrics"]["as_of_date"] = run_date
    result["metrics"]["min_rows"] = min_rows
    limitations = []
    if status == "diagnostic_only":
        limitations.append("Diagnostic leakage mode is labeled and must not be used to claim production calibration.")
    if data_source == "club_historical":
        limitations.append("Club historical calibration measures transparent goal-history baseline behavior, not the current international rating model.")
    return _write_outputs(
        result,
        as_of_date=run_date,
        data_source=data_source,
        output_dir=output_dir,
        limitations=limitations,
        run_context=run_context,
        run_tuning=run_tuning,
        tuning_profile=tuning_profile,
        primary_metric=primary_metric,
        save_tuning_candidates=save_tuning_candidates,
        apply_tuning=apply_tuning,
        holdout_season=holdout_season,
        holdout_start_date=holdout_start_date,
        holdout_end_date=holdout_end_date,
        train_start_date=train_start_date,
        train_end_date=train_end_date,
    )


def _write_outputs(
    result: dict[str, Any],
    *,
    as_of_date: str,
    data_source: str,
    output_dir: str | Path,
    limitations: list[str],
    run_context: dict[str, Any],
    run_tuning: bool = False,
    tuning_profile: str = "small",
    primary_metric: str = "composite",
    save_tuning_candidates: bool = False,
    apply_tuning: bool = False,
    holdout_season: str | None = None,
    holdout_start_date: str | None = None,
    holdout_end_date: str | None = None,
    train_start_date: str | None = None,
    train_end_date: str | None = None,
) -> dict[str, Any]:
    output = Path(run_context["run_dir"])
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output / "baseline_calibration_summary.md",
        "wdl_calibration": output / "wdl_calibration.csv",
        "totals_calibration": output / "totals_calibration.csv",
        "probability_buckets": output / "probability_buckets.csv",
        "scoreline_calibration": output / "scoreline_calibration.csv",
        "manifest": output / "calibration_manifest.json",
    }
    if data_source == "club_historical":
        paths.update({
            "club_calibration_diagnostics": output / "club_calibration_diagnostics.md",
            "club_calibration_filter_breakdown": output / "club_calibration_filter_breakdown.csv",
            "league_calibration_summary": output / "league_calibration_summary.csv",
            "league_probability_buckets": output / "league_probability_buckets.csv",
            "league_totals_calibration": output / "league_totals_calibration.csv",
            "season_calibration_summary": output / "season_calibration_summary.csv",
            "league_season_calibration_summary": output / "league_season_calibration_summary.csv",
        })
    result["wdl_calibration"].to_csv(paths["wdl_calibration"], index=False)
    result["totals_calibration"].to_csv(paths["totals_calibration"], index=False)
    result["probability_buckets"].to_csv(paths["probability_buckets"], index=False)
    result["scoreline_calibration"].to_csv(paths["scoreline_calibration"], index=False)
    if data_source == "club_historical":
        diagnostics = result.get("club_diagnostics") or {}
        filter_breakdown = result.get("club_filter_breakdown", pd.DataFrame())
        if isinstance(filter_breakdown, pd.DataFrame):
            filter_breakdown.to_csv(paths["club_calibration_filter_breakdown"], index=False)
        paths["club_calibration_diagnostics"].write_text(_club_diagnostics_markdown(diagnostics, filter_breakdown), encoding="utf-8")
        rows = result.get("rows", pd.DataFrame())
        league_summary, league_buckets, league_totals = _grouped_calibration_outputs(rows, ["league"])
        season_summary, _, _ = _grouped_calibration_outputs(rows, ["season"])
        league_season_summary, _, _ = _grouped_calibration_outputs(rows, ["league", "season"])
        league_summary.to_csv(paths["league_calibration_summary"], index=False)
        league_buckets.to_csv(paths["league_probability_buckets"], index=False)
        league_totals.to_csv(paths["league_totals_calibration"], index=False)
        season_summary.to_csv(paths["season_calibration_summary"], index=False)
        league_season_summary.to_csv(paths["league_season_calibration_summary"], index=False)
    scoreline_diagnostics = write_scoreline_diagnostics(
        result.get("rows", pd.DataFrame()),
        as_of_date=as_of_date,
        output_dir=output_dir,
        run_id=run_context["run_id"],
        min_rows=20,
    )
    manifest = {
        "run_id": run_context["run_id"],
        "calibration_run_id": run_context["run_id"],
        "run_date": as_of_date,
        "generated_at": run_context["created_at"],
        "calibration_created_at": run_context["created_at"],
        "entry_type": "baseline_calibration",
        "data_source": data_source,
        "calibration_data_source": data_source,
        "calibration_output_dir": str(output),
        "calibration_config_hash": run_context["config_hash"],
        "calibration_status": result["status"],
        "metrics": result["metrics"],
        "recommendations": result["recommendations"],
        "limitations": limitations,
        "guardrails": {
            "current_statsbomb_live_data_used": False,
            "proxy_adjustments_enabled": False,
            "betting_recommendations": False,
        },
        "style_readiness": {
            "baseline_can_support": "Rating/result calibration can establish a measurable baseline for future style layers.",
            "missing_for_style": [
                "shots for/against",
                "xG for/against",
                "open phase/set piece xG",
                "possession/field tilt proxies",
                "directness/transition proxy",
                "cards/discipline",
                "absences/injuries manual input",
            ],
            "baseline_stability_note": "Layer style adjustments only after calibration remains stable on leakage-safe rows.",
        },
        "output_paths": {key: str(path) for key, path in paths.items()},
    }
    manifest["scoreline_diagnostics"] = {
        "status": scoreline_diagnostics["manifest"]["status"],
        "diagnostic_labels": scoreline_diagnostics["manifest"]["diagnostic_labels"],
        "metrics": scoreline_diagnostics["manifest"]["metrics"],
        "paths": scoreline_diagnostics["paths"],
    }
    manifest["output_paths"].update({f"scoreline_diagnostics_{key}": value for key, value in scoreline_diagnostics["paths"].items()})
    if run_tuning:
        tuning = write_baseline_tuning_outputs(
            result.get("rows", pd.DataFrame()),
            run_dir=output,
            baseline_metrics=result["metrics"],
            tuning_profile=tuning_profile,
            primary_metric=primary_metric,
            save_tuning_candidates=save_tuning_candidates,
            apply_tuning=apply_tuning,
            holdout_season=holdout_season,
            holdout_start_date=holdout_start_date,
            holdout_end_date=holdout_end_date,
            train_start_date=train_start_date,
            train_end_date=train_end_date,
        )
        manifest["baseline_tuning"] = tuning["manifest"]
        manifest["output_paths"].update(tuning["paths"])
    else:
        manifest["baseline_tuning"] = {"status": "not_requested", "diagnostic_only": True, "production_defaults_changed": False}
    paths["manifest"].write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    paths["summary"].write_text(_summary_markdown(manifest, result), encoding="utf-8")
    _write_latest_manifests(manifest, run_context)
    _write_calibration_run_index(Path(output_dir) / as_of_date)
    _write_calibration_comparison_summary(Path(output_dir) / as_of_date)
    all_paths = {key: str(path) for key, path in paths.items()}
    all_paths.update(manifest["output_paths"])
    return {**result, "manifest": manifest, "paths": all_paths, "run_dir": output}


def _write_latest_manifests(manifest: dict[str, Any], run_context: dict[str, Any]) -> None:
    latest = _latest_manifest_payload(manifest)
    date_latest = Path(run_context["date_dir"]) / "latest_manifest.json"
    source_latest = Path(run_context["source_dir"]) / "latest_manifest.json"
    date_latest.parent.mkdir(parents=True, exist_ok=True)
    source_latest.parent.mkdir(parents=True, exist_ok=True)
    date_latest.write_text(json.dumps(latest, indent=2, default=str), encoding="utf-8")
    source_latest.write_text(json.dumps(latest, indent=2, default=str), encoding="utf-8")


def _write_calibration_run_index(date_dir: Path) -> Path:
    manifests = sorted(date_dir.glob("*/*/calibration_manifest.json"))
    rows: list[dict[str, Any]] = []
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        metrics = manifest.get("metrics") or {}
        tuning = manifest.get("baseline_tuning") or {}
        rows.append({
            "run_id": manifest.get("calibration_run_id") or manifest.get("run_id"),
            "data_source": manifest.get("calibration_data_source") or manifest.get("data_source"),
            "created_at": manifest.get("calibration_created_at") or manifest.get("generated_at"),
            "status": manifest.get("calibration_status"),
            "row_count": metrics.get("row_count"),
            "leakage_status": "leakage_safe" if metrics.get("leakage_safe") else "diagnostic_or_blocked",
            "wdl_log_loss": metrics.get("wdl_log_loss"),
            "brier_score": metrics.get("brier_score"),
            "total_goals_mae": metrics.get("total_goals_mae"),
            "over_2_5_brier": metrics.get("over_under_2_5_brier_score"),
            "recommendation": "; ".join(map(str, manifest.get("recommendations") or [])),
            "tuning_status": tuning.get("status", "not_requested"),
            "tuning_recommendation": tuning.get("best_recommendation", ""),
            "output_dir": manifest.get("calibration_output_dir") or str(manifest_path.parent),
        })
    index_path = date_dir / "calibration_run_index.csv"
    pd.DataFrame(rows, columns=[
        "run_id",
        "data_source",
        "created_at",
        "status",
        "row_count",
        "leakage_status",
        "wdl_log_loss",
        "brier_score",
        "total_goals_mae",
        "over_2_5_brier",
        "recommendation",
        "tuning_status",
        "tuning_recommendation",
        "output_dir",
    ]).to_csv(index_path, index=False)
    return index_path


def _write_calibration_comparison_summary(date_dir: Path) -> Path:
    latest_by_source: dict[str, dict[str, Any]] = {}
    for manifest_path in sorted(date_dir.glob("*/*/calibration_manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        source = str(manifest.get("calibration_data_source") or manifest.get("data_source") or "")
        if source not in {"club_historical", "international_historical"}:
            continue
        current = latest_by_source.get(source)
        if current is None or str(manifest.get("calibration_created_at") or "") > str(current.get("calibration_created_at") or ""):
            latest_by_source[source] = manifest
    rows = []
    for source in ["club_historical", "international_historical"]:
        manifest = latest_by_source.get(source)
        if not manifest:
            rows.append({"data_source": source, "status": "missing_latest_run"})
            continue
        metrics = manifest.get("metrics") or {}
        tuning = manifest.get("baseline_tuning") or {}
        rows.append({
            "data_source": source,
            "status": manifest.get("calibration_status"),
            "row_count": metrics.get("row_count"),
            "wdl_log_loss": metrics.get("wdl_log_loss"),
            "brier_score": metrics.get("brier_score"),
            "accuracy": metrics.get("accuracy"),
            "total_goals_mae": metrics.get("total_goals_mae"),
            "over_2_5_brier": metrics.get("over_under_2_5_brier_score"),
            "most_likely_score_hit_rate": metrics.get("most_likely_score_hit_rate"),
            "recommendation": "; ".join(map(str, manifest.get("recommendations") or [])),
            "tuning_recommendation": tuning.get("best_recommendation", ""),
            "output_dir": manifest.get("calibration_output_dir"),
        })
    frame = pd.DataFrame(rows)
    path = date_dir / "calibration_comparison_summary.md"
    lines = [
        "# Calibration Comparison Summary",
        "",
        "This compares latest club and international calibration runs. It does not combine them into one model.",
        "",
        _markdown_table(frame),
        "",
        "## Guardrails",
        "",
        "- Production defaults are unchanged.",
        "- Club and international calibration remain separate.",
        "- Current StatsBomb live data is not used.",
        "- No betting recommendations are produced.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _club_diagnostics_markdown(diagnostics: dict[str, Any], filter_breakdown: pd.DataFrame | None) -> str:
    inventory = pd.DataFrame(diagnostics.get("path_inventory") or [])
    lines = [
        "# Club Calibration Diagnostics",
        "",
        f"- Selected path: `{diagnostics.get('selected_path', '')}`",
        f"- Total raw rows found: `{diagnostics.get('total_raw_rows_found', 0)}`",
        f"- Date range: `{diagnostics.get('date_min', '')}` to `{diagnostics.get('date_max', '')}`",
        f"- Leagues found: `{', '.join(map(str, diagnostics.get('leagues_found') or []))}`",
        f"- Seasons found: `{', '.join(map(str, diagnostics.get('seasons_found') or []))}`",
        f"- Reason blocked: `{diagnostics.get('reason_blocked', '')}`",
        f"- Suggested repair: {diagnostics.get('suggested_repair', '')}",
        "",
        "## Paths Checked",
        "",
    ]
    if inventory.empty:
        lines.append("_No path inventory available._")
    else:
        lines.append(_markdown_table(inventory))
    lines.extend(["", "## Filter Breakdown", ""])
    if filter_breakdown is not None and not filter_breakdown.empty:
        lines.append(_markdown_table(filter_breakdown))
    else:
        lines.append("_No filter breakdown available._")
    rebuild = diagnostics.get("rebuild_from_raw") or {}
    if rebuild:
        lines.extend([
            "",
            "## Rebuild From Raw",
            "",
            _markdown_table(pd.DataFrame([rebuild])),
        ])
    return "\n".join(lines)


def _summary_markdown(manifest: dict[str, Any], result: dict[str, Any]) -> str:
    metrics = manifest["metrics"]
    lines = [
        "# Baseline Calibration",
        "",
        f"- Calibration run ID: `{manifest['calibration_run_id']}`",
        f"- Calibration status: `{manifest['calibration_status']}`",
        f"- Data source: `{manifest['calibration_data_source']}`",
        f"- Output directory: `{manifest['calibration_output_dir']}`",
        f"- Config hash: `{manifest['calibration_config_hash']}`",
        f"- Row count: `{metrics.get('row_count')}`",
        f"- Leakage safe: `{metrics.get('leakage_safe')}`",
        f"- W/D/L log loss: `{metrics.get('wdl_log_loss')}`",
        f"- Brier score: `{metrics.get('brier_score')}`",
        f"- O/U 2.5 Brier score: `{metrics.get('over_under_2_5_brier_score')}`",
        f"- Most likely score hit rate: `{metrics.get('most_likely_score_hit_rate')}`",
        "",
        "## Calibration Recommendations",
        "",
        *[f"- `{item}`" for item in manifest["recommendations"]],
        "",
        "## Limitations",
        "",
    ]
    if manifest["limitations"]:
        lines.extend(f"- {item}" for item in manifest["limitations"])
    else:
        lines.append("- No extra limitations beyond normal baseline validation caveats.")
    lines.extend([
        "",
        "## Style Readiness",
        "",
        f"- Baseline can support now: {manifest['style_readiness']['baseline_can_support']}",
        f"- Baseline stability note: {manifest['style_readiness']['baseline_stability_note']}",
        "- Most valuable missing style inputs:",
        *[f"  - {item}" for item in manifest["style_readiness"]["missing_for_style"]],
        "",
        "## Guardrails",
        "",
        "- Current StatsBomb is not used as live data.",
        "- Proxy adjustments remain disabled.",
        "- This report measures calibration; tuning output is diagnostic-only when requested.",
        "- No betting recommendations are produced.",
        "",
    ])
    tuning = manifest.get("baseline_tuning") or {}
    lines.extend([
        "## Baseline Tuning",
        "",
        f"- Status: `{tuning.get('status', 'not_requested')}`",
        f"- Production defaults changed: `{tuning.get('production_defaults_changed', False)}`",
        "",
    ])
    if not result["probability_buckets"].empty:
        lines.extend(["## Probability Buckets", "", _markdown_table(result["probability_buckets"].head(20)), ""])
    if not result["totals_calibration"].empty:
        lines.extend(["## O/U 2.5 Calibration", "", _markdown_table(result["totals_calibration"].head(20)), ""])
    return "\n".join(lines)


def write_baseline_tuning_diagnostics(rows: pd.DataFrame, *, as_of_date: str, output_dir: str | Path = "outputs/calibration") -> dict[str, Any]:
    run_dir = Path(output_dir) / as_of_date
    baseline_rows = rows.copy()
    if not baseline_rows.empty and {"home_rating", "away_rating", "home_goals", "away_goals"}.issubset(baseline_rows.columns):
        baseline_rows = project_rows_with_candidate(baseline_rows, default_rating_baseline_parameters())
        baseline_metrics = evaluate_projection_calibration(baseline_rows, data_source="baseline_tuning_current_baseline")["metrics"]
    else:
        baseline_metrics = _empty_metrics("blocked_insufficient_rows", "baseline_tuning_current_baseline", 0)
    return write_baseline_tuning_outputs(
        rows,
        run_dir=run_dir,
        baseline_metrics=baseline_metrics,
        tuning_profile="small",
        primary_metric="composite",
        save_tuning_candidates=False,
        apply_tuning=False,
    )


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(row.get(col, "")).replace("|", "\\|") for col in columns) + " |")
    return "\n".join(lines)


def format_calibration_terminal(result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    return "\n".join([
        "Baseline Calibration",
        f"Status: {result['status']}",
        f"Data source: {metrics.get('data_source')}",
        f"Rows: {metrics.get('row_count')}",
        f"Leakage safe: {metrics.get('leakage_safe')}",
        f"W/D/L log loss: {metrics.get('wdl_log_loss')}",
        f"Brier score: {metrics.get('brier_score')}",
        f"Total goals MAE: {metrics.get('total_goals_mae')}",
        f"O/U 2.5 Brier: {metrics.get('over_under_2_5_brier_score')}",
        f"Most likely score hit rate: {metrics.get('most_likely_score_hit_rate')}",
        f"Recommendations: {', '.join(result['recommendations'])}",
        f"Run dir: {result.get('run_dir')}",
        f"Summary: {result['paths']['summary']}",
    ])
