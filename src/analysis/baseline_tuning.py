from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.models.score_projection import _projection_from_xg


TUNING_RECOMMENDATIONS = {
    "keep_current_baseline",
    "candidate_improves_wdl",
    "candidate_improves_totals",
    "candidate_balanced_improvement",
    "candidate_overfits_or_unstable",
    "insufficient_rows",
    "needs_holdout_validation",
    "totals_still_too_low",
    "totals_improved_wdl_hurt",
}

MAX_TUNING_ROWS = 500


def default_rating_baseline_parameters() -> dict[str, float]:
    return {
        "rating_diff_to_goal_scale": 900.0,
        "baseline_total_goals": 2.35,
        "neutral_home_adjustment": 0.0,
        "draw_dampening": 1.0,
        "total_goals_adjustment": 0.0,
    }


def _limit_tuning_rows(rows: pd.DataFrame, limit: int = MAX_TUNING_ROWS) -> pd.DataFrame:
    if len(rows) <= limit:
        return rows.copy()
    ordered = rows.sort_values("date").reset_index(drop=True) if "date" in rows.columns else rows.reset_index(drop=True)
    indices = np.linspace(0, len(ordered) - 1, limit).round().astype(int)
    return ordered.iloc[sorted(set(indices))].copy()


def tuning_grid(profile: str = "small") -> list[dict[str, float]]:
    if profile == "wide":
        scales = [600.0, 750.0, 900.0, 1050.0, 1200.0]
        totals = [2.05, 2.2, 2.35, 2.5, 2.65]
        neutral = [-0.06, 0.0, 0.06]
        draw = [0.9, 1.0, 1.08]
        total_adj = [-0.15, 0.0, 0.15]
    elif profile == "medium":
        scales = [700.0, 850.0, 1000.0, 1150.0]
        totals = [2.15, 2.3, 2.45, 2.6]
        neutral = [-0.04, 0.0, 0.04]
        draw = [0.94, 1.0, 1.05]
        total_adj = [-0.1, 0.0, 0.1]
    else:
        scales = [750.0, 900.0, 1050.0]
        totals = [2.25, 2.45]
        neutral = [0.0]
        draw = [1.0]
        total_adj = [0.0]
    return [
        {
            "rating_diff_to_goal_scale": scale,
            "baseline_total_goals": base_total,
            "neutral_home_adjustment": home_adj,
            "draw_dampening": draw_damp,
            "total_goals_adjustment": goals_adj,
        }
        for scale in scales
        for base_total in totals
        for home_adj in neutral
        for draw_damp in draw
        for goals_adj in total_adj
    ]


def project_candidate_xg(home_rating: float, away_rating: float, params: dict[str, Any]) -> dict[str, Any]:
    scale = max(100.0, float(params.get("rating_diff_to_goal_scale", 900.0)))
    base_total = float(params.get("baseline_total_goals", 2.35))
    home_adjustment = float(params.get("neutral_home_adjustment", 0.0))
    total_adjustment = float(params.get("total_goals_adjustment", 0.0))
    diff = max(-350.0, min(350.0, float(home_rating) - float(away_rating)))
    total = max(1.6, min(3.2, base_total + total_adjustment + abs(diff) / scale * 0.18))
    home_share = 0.5 + max(-0.18, min(0.18, diff / scale)) + home_adjustment
    home_share = max(0.28, min(0.72, home_share))
    home_xg = round(max(0.35, total * home_share), 3)
    away_xg = round(max(0.35, total * (1 - home_share)), 3)
    probs = _projection_from_xg(home_xg, away_xg)
    probs = _apply_draw_dampening(probs, float(params.get("draw_dampening", 1.0)))
    return {
        "home_xg": home_xg,
        "away_xg": away_xg,
        "projected_total": round(home_xg + away_xg, 3),
        **probs,
    }


def project_rows_with_candidate(rows: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    home_strength, away_strength = _strength_columns(rows)
    projected: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        candidate = project_candidate_xg(float(row[home_strength]), float(row[away_strength]), params)
        projected.append({
            "date": row.get("date", ""),
            "league": row.get("league", ""),
            "season": row.get("season", ""),
            "home_team": row.get("home_team", ""),
            "away_team": row.get("away_team", ""),
            "home_goals": row["home_goals"],
            "away_goals": row["away_goals"],
            "home_xg": candidate["home_xg"],
            "away_xg": candidate["away_xg"],
            "home_win_prob": candidate["home_win_prob"],
            "draw_prob": candidate["draw_prob"],
            "away_win_prob": candidate["away_win_prob"],
            "over_2_5_prob": candidate["over_2_5_prob"],
            "most_likely_score": candidate["most_likely_score"],
        })
    return pd.DataFrame(projected)


def evaluate_tuning_grid(
    rows: pd.DataFrame,
    *,
    profile: str = "small",
    primary_metric: str = "composite",
    baseline_metrics: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from src.analysis.baseline_calibration import evaluate_projection_calibration

    if rows.empty or not {"home_goals", "away_goals"}.issubset(rows.columns) or _strength_columns(rows) == ("", ""):
        grid = pd.DataFrame([{
            "diagnostic_status": "blocked_insufficient_rows",
            "recommendation": "insufficient_rows",
            "reason": "Rating-backed rows or measured strength-index rows are required for baseline tuning diagnostics.",
        }])
        return grid, grid.copy()
    baseline = baseline_metrics or evaluate_projection_calibration(rows, data_source="baseline_tuning_current_baseline")["metrics"]
    grid_rows: list[dict[str, Any]] = []
    for params in tuning_grid(profile):
        projected = project_rows_with_candidate(rows, params)
        eval_result = evaluate_projection_calibration(projected, data_source="baseline_tuning_diagnostic")
        metrics = eval_result["metrics"]
        record = {
            "diagnostic_status": "diagnostic_only",
            **params,
            "rows": metrics["row_count"],
            "wdl_log_loss": metrics["wdl_log_loss"],
            "brier_score": metrics["brier_score"],
            "total_goals_mae": metrics["total_goals_mae"],
            "over_2_5_brier": metrics["over_under_2_5_brier_score"],
            "most_likely_score_hit_rate": metrics["most_likely_score_hit_rate"],
            "mean_projected_total": metrics.get("mean_projected_total"),
            "mean_actual_total": metrics.get("mean_actual_total"),
        }
        record["composite_score"] = _composite_score(record)
        record["wdl_log_loss_delta"] = _delta(record["wdl_log_loss"], baseline.get("wdl_log_loss"))
        record["total_goals_mae_delta"] = _delta(record["total_goals_mae"], baseline.get("total_goals_mae"))
        record["over_2_5_brier_delta"] = _delta(record["over_2_5_brier"], baseline.get("over_under_2_5_brier_score"))
        record["recommendation"] = recommendation_for_candidate(record, baseline)
        grid_rows.append(record)
    grid = pd.DataFrame(grid_rows)
    sort_metric = _primary_sort_column(primary_metric)
    best = grid.sort_values([sort_metric, "wdl_log_loss", "total_goals_mae"], ascending=[True, True, True]).head(10).copy()
    return grid, best


def write_baseline_tuning_outputs(
    rows: pd.DataFrame,
    *,
    run_dir: str | Path,
    baseline_metrics: dict[str, Any],
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
    output = Path(run_dir) / "baseline_tuning"
    output.mkdir(parents=True, exist_ok=True)
    original_row_count = int(len(rows))
    rows = _limit_tuning_rows(rows)
    paths = {
        "baseline_tuning_summary": output / "baseline_tuning_summary.md",
        "baseline_tuning_grid": output / "baseline_tuning_grid.csv",
        "baseline_tuning_best_candidates": output / "baseline_tuning_best_candidates.csv",
        "baseline_tuning_manifest": output / "baseline_tuning_manifest.json",
    }
    train_rows, holdout_rows, holdout_status = _split_train_holdout(
        rows,
        holdout_season=holdout_season,
        holdout_start_date=holdout_start_date,
        holdout_end_date=holdout_end_date,
        train_start_date=train_start_date,
        train_end_date=train_end_date,
    )
    fit_rows = train_rows if holdout_status == "holdout_available" else rows
    grid, best = evaluate_tuning_grid(
        fit_rows,
        profile=tuning_profile,
        primary_metric=primary_metric,
        baseline_metrics=baseline_metrics,
    )
    grid.to_csv(paths["baseline_tuning_grid"], index=False)
    best.to_csv(paths["baseline_tuning_best_candidates"], index=False)
    candidate_config_path = ""
    candidate_params: dict[str, Any] = {}
    if not best.empty and "diagnostic_status" in best and str(best.iloc[0]["diagnostic_status"]) == "diagnostic_only":
        candidate_params = _candidate_params_from_row(best.iloc[0])
    if candidate_params and (save_tuning_candidates or apply_tuning):
        candidate = {
            "config_type": "diagnostic_candidate_model_config",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "production_defaults_changed": False,
            "apply_tuning_requested": bool(apply_tuning),
            "warning": "Diagnostic-only candidate. It is not applied to production defaults automatically.",
            "primary_metric": primary_metric,
            "tuning_profile": tuning_profile,
            "model_parameters": candidate_params,
            "best_candidate_metrics": best.iloc[0].to_dict(),
        }
        candidate_path = output / "candidate_model_config.json"
        candidate_path.write_text(json.dumps(candidate, indent=2, default=str), encoding="utf-8")
        paths["candidate_model_config"] = candidate_path
        candidate_config_path = str(candidate_path)
    holdout_paths: dict[str, Path] = {}
    holdout_summary: dict[str, Any] = {"status": holdout_status}
    if holdout_status != "not_requested":
        holdout_paths = _write_holdout_outputs(
            output,
            train_rows=train_rows,
            holdout_rows=holdout_rows,
            candidate_params=candidate_params,
        )
        paths.update(holdout_paths)
        holdout_summary = _holdout_summary_payload(holdout_paths)
    summary = _summary_markdown(
        status="diagnostic_only" if str(grid.iloc[0].get("diagnostic_status", "")) == "diagnostic_only" else str(grid.iloc[0].get("diagnostic_status", "blocked_insufficient_rows")),
        tuning_profile=tuning_profile,
        primary_metric=primary_metric,
        rows=len(rows),
        best=best,
        candidate_config_path=candidate_config_path,
        holdout_summary=holdout_summary,
    )
    paths["baseline_tuning_summary"].write_text(summary, encoding="utf-8")
    manifest = {
        "status": "diagnostic_only" if candidate_params else "blocked_insufficient_rows",
        "diagnostic_only": True,
        "rows": original_row_count,
        "rows_evaluated": int(len(rows)),
        "row_sampling": "deterministic_even_sample" if len(rows) < original_row_count else "none",
        "tuning_profile": tuning_profile,
        "primary_metric": primary_metric,
        "strength_input_columns": _strength_columns(rows),
        "candidate_config_written": bool(candidate_config_path),
        "production_defaults_changed": False,
        "holdout": holdout_summary,
        "best_recommendation": "" if best.empty else str(best.iloc[0].get("recommendation", "")),
        "best_candidate": {} if best.empty else best.iloc[0].to_dict(),
        "paths": {key: str(path) for key, path in paths.items()},
    }
    paths["baseline_tuning_manifest"].write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return {
        "manifest": manifest,
        "paths": {key: str(path) for key, path in paths.items()},
        "grid": grid,
        "best": best,
    }


def recommendation_for_candidate(candidate: dict[str, Any], baseline: dict[str, Any]) -> str:
    rows = int(candidate.get("rows") or 0)
    if rows < 20:
        return "insufficient_rows"
    wdl_delta = _delta(candidate.get("wdl_log_loss"), baseline.get("wdl_log_loss"))
    totals_delta = _delta(candidate.get("total_goals_mae"), baseline.get("total_goals_mae"))
    ou_delta = _delta(candidate.get("over_2_5_brier"), baseline.get("over_under_2_5_brier_score"))
    actual_total = candidate.get("mean_actual_total")
    projected_total = candidate.get("mean_projected_total")
    if projected_total is not None and actual_total is not None and float(projected_total) < float(actual_total) - 0.12:
        return "totals_still_too_low"
    if totals_delta < -0.03 and wdl_delta > 0.02:
        return "totals_improved_wdl_hurt"
    if wdl_delta < -0.01 and totals_delta < -0.03 and ou_delta <= 0.01:
        return "candidate_balanced_improvement"
    if wdl_delta < -0.01:
        return "candidate_improves_wdl"
    if totals_delta < -0.03 or ou_delta < -0.01:
        return "candidate_improves_totals"
    return "keep_current_baseline"


def _apply_draw_dampening(probs: dict[str, Any], draw_dampening: float) -> dict[str, Any]:
    if abs(draw_dampening - 1.0) < 1e-9:
        return probs
    home = float(probs["home_win_prob"])
    draw = max(0.001, float(probs["draw_prob"]) * max(0.5, min(1.5, draw_dampening)))
    away = float(probs["away_win_prob"])
    total = max(0.001, home + draw + away)
    adjusted = dict(probs)
    adjusted["home_win_prob"] = home / total
    adjusted["draw_prob"] = draw / total
    adjusted["away_win_prob"] = away / total
    return adjusted


def _composite_score(record: dict[str, Any]) -> float:
    return float(record["wdl_log_loss"]) + float(record["brier_score"]) + float(record["over_2_5_brier"]) + 0.25 * float(record["total_goals_mae"])


def _primary_sort_column(primary_metric: str) -> str:
    return {
        "wdl_log_loss": "wdl_log_loss",
        "brier": "brier_score",
        "total_goals_mae": "total_goals_mae",
        "over_2_5_brier": "over_2_5_brier",
        "composite": "composite_score",
    }.get(primary_metric, "composite_score")


def _delta(value: Any, baseline: Any) -> float:
    try:
        return float(value) - float(baseline)
    except (TypeError, ValueError):
        return 0.0


def _candidate_params_from_row(row: pd.Series) -> dict[str, float]:
    keys = [
        "rating_diff_to_goal_scale",
        "baseline_total_goals",
        "neutral_home_adjustment",
        "draw_dampening",
        "total_goals_adjustment",
    ]
    return {key: float(row[key]) for key in keys if key in row}


def _strength_columns(rows: pd.DataFrame) -> tuple[str, str]:
    if {"home_rating", "away_rating"}.issubset(rows.columns):
        return "home_rating", "away_rating"
    if {"home_strength_index", "away_strength_index"}.issubset(rows.columns):
        return "home_strength_index", "away_strength_index"
    return "", ""


def _split_train_holdout(
    rows: pd.DataFrame,
    *,
    holdout_season: str | None,
    holdout_start_date: str | None,
    holdout_end_date: str | None,
    train_start_date: str | None,
    train_end_date: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    requested = any([holdout_season, holdout_start_date, holdout_end_date, train_start_date, train_end_date])
    if not requested:
        return rows.copy(), pd.DataFrame(), "not_requested"
    data = rows.copy()
    if "date" in data:
        data["_date"] = pd.to_datetime(data["date"], errors="coerce")
    else:
        data["_date"] = pd.NaT
    train_mask = pd.Series(True, index=data.index)
    holdout_mask = pd.Series(False, index=data.index)
    if holdout_season and "season" in data:
        holdout_mask = data["season"].astype(str).eq(str(holdout_season))
    if holdout_start_date:
        holdout_mask |= data["_date"].ge(pd.to_datetime(holdout_start_date, errors="coerce"))
    if holdout_end_date:
        holdout_mask &= data["_date"].le(pd.to_datetime(holdout_end_date, errors="coerce"))
    if train_start_date:
        train_mask &= data["_date"].ge(pd.to_datetime(train_start_date, errors="coerce"))
    if train_end_date:
        train_mask &= data["_date"].le(pd.to_datetime(train_end_date, errors="coerce"))
    train = data[train_mask & ~holdout_mask].drop(columns=["_date"], errors="ignore").copy()
    holdout = data[holdout_mask].drop(columns=["_date"], errors="ignore").copy()
    if train.empty or holdout.empty:
        return train, holdout, "needs_holdout_validation"
    return train, holdout, "holdout_available"


def _write_holdout_outputs(output: Path, *, train_rows: pd.DataFrame, holdout_rows: pd.DataFrame, candidate_params: dict[str, Any]) -> dict[str, Path]:
    from src.analysis.baseline_calibration import evaluate_projection_calibration

    paths = {
        "train_metrics": output / "train_metrics.csv",
        "holdout_metrics": output / "holdout_metrics.csv",
        "tuning_holdout_summary": output / "tuning_holdout_summary.md",
    }
    rows_by_split = {"train": train_rows, "holdout": holdout_rows}
    metrics_frames: dict[str, pd.DataFrame] = {}
    for split, frame in rows_by_split.items():
        records: list[dict[str, Any]] = []
        if not frame.empty:
            baseline = evaluate_projection_calibration(frame, data_source=f"{split}_baseline")["metrics"]
            records.append({"model": "current_baseline", **baseline})
            if candidate_params:
                candidate_rows = project_rows_with_candidate(frame, candidate_params)
                candidate = evaluate_projection_calibration(candidate_rows, data_source=f"{split}_candidate")["metrics"]
                records.append({"model": "diagnostic_candidate", **candidate})
        metrics_frames[split] = pd.DataFrame(records)
        if metrics_frames[split].empty:
            metrics_frames[split] = pd.DataFrame(columns=["model", "calibration_status", "data_source", "row_count", "wdl_log_loss", "brier_score", "total_goals_mae"])
    metrics_frames["train"].to_csv(paths["train_metrics"], index=False)
    metrics_frames["holdout"].to_csv(paths["holdout_metrics"], index=False)
    lines = [
        "# Tuning Holdout Summary",
        "",
        "- Diagnostic only; production defaults are unchanged.",
        f"- Train rows: `{len(train_rows)}`",
        f"- Holdout rows: `{len(holdout_rows)}`",
    ]
    if holdout_rows.empty or train_rows.empty:
        lines.append("- Recommendation: `needs_holdout_validation`")
    elif len(metrics_frames["holdout"]) >= 2:
        baseline = metrics_frames["holdout"].iloc[0]
        candidate = metrics_frames["holdout"].iloc[1]
        wdl_delta = _delta(candidate.get("wdl_log_loss"), baseline.get("wdl_log_loss"))
        totals_delta = _delta(candidate.get("total_goals_mae"), baseline.get("total_goals_mae"))
        label = "candidate_balanced_improvement" if wdl_delta <= 0 and totals_delta <= 0 else "candidate_overfits_or_unstable"
        lines.extend([
            f"- Holdout W/D/L log-loss delta: `{wdl_delta}`",
            f"- Holdout total-goals MAE delta: `{totals_delta}`",
            f"- Recommendation: `{label}`",
        ])
    paths["tuning_holdout_summary"].write_text("\n".join(lines), encoding="utf-8")
    return paths


def _holdout_summary_payload(paths: dict[str, Path]) -> dict[str, Any]:
    payload = {"status": "holdout_available", "paths": {key: str(path) for key, path in paths.items()}}
    try:
        holdout = pd.read_csv(paths["holdout_metrics"]) if paths.get("holdout_metrics") and paths["holdout_metrics"].exists() else pd.DataFrame()
    except pd.errors.EmptyDataError:
        holdout = pd.DataFrame()
    if holdout.empty:
        payload["status"] = "needs_holdout_validation"
        payload["recommendation"] = "needs_holdout_validation"
        return payload
    payload["holdout_rows"] = int(holdout.get("row_count", pd.Series(dtype=float)).max() or 0)
    if len(holdout) >= 2:
        baseline = holdout.iloc[0]
        candidate = holdout.iloc[1]
        payload["wdl_log_loss_delta"] = _delta(candidate.get("wdl_log_loss"), baseline.get("wdl_log_loss"))
        payload["total_goals_mae_delta"] = _delta(candidate.get("total_goals_mae"), baseline.get("total_goals_mae"))
        payload["recommendation"] = "candidate_balanced_improvement" if payload["wdl_log_loss_delta"] <= 0 and payload["total_goals_mae_delta"] <= 0 else "candidate_overfits_or_unstable"
    return payload


def _summary_markdown(
    *,
    status: str,
    tuning_profile: str,
    primary_metric: str,
    rows: int,
    best: pd.DataFrame,
    candidate_config_path: str,
    holdout_summary: dict[str, Any],
) -> str:
    lines = [
        "# Baseline Tuning Diagnostics",
        "",
        f"- Status: `{status}`",
        f"- Rows: `{rows}`",
        f"- Tuning profile: `{tuning_profile}`",
        f"- Primary metric: `{primary_metric}`",
        "- Diagnostic only; production defaults are not changed.",
        "- Candidate configs are preview inputs only and require separate review.",
    ]
    if candidate_config_path:
        lines.append(f"- Candidate config: `{candidate_config_path}`")
    if holdout_summary.get("status") != "not_requested":
        lines.append(f"- Holdout status: `{holdout_summary.get('status')}`")
        if holdout_summary.get("recommendation"):
            lines.append(f"- Holdout recommendation: `{holdout_summary.get('recommendation')}`")
    if not best.empty:
        lines.extend([
            "",
            "## Best Candidates",
            "",
            _markdown_table(best.head(5)),
        ])
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    cols = list(frame.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(row.get(col, "")).replace("|", "\\|") for col in cols) + " |")
    return "\n".join(lines)
