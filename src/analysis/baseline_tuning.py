from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.models.score_projection import _projection_from_xg, score_distribution


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
    "balanced_improvement",
    "totals_improved_wdl_stable",
    "scoreline_spread_improved",
    "favorites_uncapped_improved",
    "overfit_risk",
    "limited_holdout_confidence",
}

MAX_TUNING_ROWS = 500


def default_rating_baseline_parameters() -> dict[str, float]:
    return {
        "rating_diff_to_goal_scale": 900.0,
        "baseline_total_goals": 2.35,
        "neutral_home_adjustment": 0.0,
        "draw_dampening": 1.0,
        "total_goals_adjustment": 0.0,
        "favorite_xg_spread_multiplier": 1.0,
        "underdog_xg_floor": 0.0,
        "underdog_xg_scale": 1.0,
        "home_or_neutral_adjustment": 0.0,
        "scoreline_dispersion_multiplier": 1.0,
    }


def _limit_tuning_rows(rows: pd.DataFrame, limit: int = MAX_TUNING_ROWS) -> pd.DataFrame:
    if len(rows) <= limit:
        return rows.copy()
    ordered = rows.sort_values("date").reset_index(drop=True) if "date" in rows.columns else rows.reset_index(drop=True)
    indices = np.linspace(0, len(ordered) - 1, limit).round().astype(int)
    return ordered.iloc[sorted(set(indices))].copy()


def tuning_grid(profile: str = "small") -> list[dict[str, float]]:
    if profile == "wide":
        scales = [700.0, 900.0, 1100.0]
        totals = [2.25, 2.45, 2.65]
        neutral = [0.0]
        draw = [1.0]
        total_adj = [0.0, 0.1]
        spread = [1.0, 1.18]
        floors = [0.0, 0.25]
        underdog_scales = [1.0]
        dispersion = [1.0, 1.08]
    elif profile == "medium":
        scales = [750.0, 900.0, 1050.0]
        totals = [2.25, 2.45, 2.6]
        neutral = [0.0, 0.04]
        draw = [1.0]
        total_adj = [0.0, 0.1]
        spread = [1.0, 1.12]
        floors = [0.0, 0.25]
        underdog_scales = [1.0]
        dispersion = [1.0, 1.05]
    else:
        scales = [750.0, 900.0, 1050.0]
        totals = [2.25, 2.45]
        neutral = [0.0]
        draw = [1.0]
        total_adj = [0.0]
        spread = [1.0]
        floors = [0.0, 0.25]
        underdog_scales = [1.0]
        dispersion = [1.0]
    return [
        {
            "rating_diff_to_goal_scale": scale,
            "baseline_total_goals": base_total,
            "neutral_home_adjustment": home_adj,
            "draw_dampening": draw_damp,
            "total_goals_adjustment": goals_adj,
            "favorite_xg_spread_multiplier": spread_multiplier,
            "underdog_xg_floor": underdog_floor,
            "underdog_xg_scale": underdog_scale,
            "home_or_neutral_adjustment": home_adj,
            "scoreline_dispersion_multiplier": dispersion_multiplier,
        }
        for scale in scales
        for base_total in totals
        for home_adj in neutral
        for draw_damp in draw
        for goals_adj in total_adj
        for spread_multiplier in spread
        for underdog_floor in floors
        for underdog_scale in underdog_scales
        for dispersion_multiplier in dispersion
    ]


def project_candidate_xg(home_rating: float, away_rating: float, params: dict[str, Any]) -> dict[str, Any]:
    scale = max(100.0, float(params.get("rating_diff_to_goal_scale", 900.0)))
    base_total = float(params.get("baseline_total_goals", 2.35))
    home_adjustment = float(params.get("home_or_neutral_adjustment", params.get("neutral_home_adjustment", 0.0)))
    total_adjustment = float(params.get("total_goals_adjustment", 0.0))
    diff = float(home_rating) - float(away_rating)
    dispersion = max(0.7, min(1.4, float(params.get("scoreline_dispersion_multiplier", 1.0))))
    total = (base_total + total_adjustment + math.log1p(abs(diff)) / math.log1p(scale + 1.0) * 0.30) * dispersion
    spread_multiplier = max(0.6, min(1.5, float(params.get("favorite_xg_spread_multiplier", 1.0))))
    home_share = 0.5 + 0.28 * math.tanh(diff / scale * spread_multiplier) + home_adjustment
    home_share = max(0.05, min(0.95, home_share))
    raw_home = total * home_share
    raw_away = total * (1 - home_share)
    floor = max(0.0, min(0.7, float(params.get("underdog_xg_floor", 0.0))))
    underdog_scale = max(0.5, min(1.5, float(params.get("underdog_xg_scale", 1.0))))
    if diff >= 0:
        raw_away = max(floor, raw_away * underdog_scale)
    else:
        raw_home = max(floor, raw_home * underdog_scale)
    home_guarded, home_guard, home_reason = _xg_safety_guard(raw_home, "home")
    away_guarded, away_guard, away_reason = _xg_safety_guard(raw_away, "away")
    home_xg = round(home_guarded, 3)
    away_xg = round(away_guarded, 3)
    probs = _projection_from_xg(home_xg, away_xg)
    probs = _apply_draw_dampening(probs, float(params.get("draw_dampening", 1.0)))
    return {
        "home_xg": home_xg,
        "away_xg": away_xg,
        "projected_total": round(home_xg + away_xg, 3),
        "xg_safety_guard_applied": bool(home_guard or away_guard),
        "xg_safety_guard_reason": " | ".join(reason for reason in [home_reason, away_reason] if reason),
        **probs,
    }


def _xg_safety_guard(value: float, side: str) -> tuple[float, bool, str]:
    if pd.isna(value):
        return 1.0, True, f"{side} xG missing; neutral diagnostic fallback used"
    if value < 0.0:
        return 0.0, True, f"{side} xG raised from negative value"
    if value > 5.0:
        return 5.0, True, f"{side} xG lowered by broad 5.00 sanity guard"
    return value, False, ""


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
            "btts_prob": candidate.get("btts_prob"),
            "most_likely_score": candidate["most_likely_score"],
            "xg_safety_guard_applied": candidate["xg_safety_guard_applied"],
            "xg_safety_guard_reason": candidate["xg_safety_guard_reason"],
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
    from src.analysis.scoreline_calibration import evaluate_scoreline_calibration

    if rows.empty or not {"home_goals", "away_goals"}.issubset(rows.columns) or _strength_columns(rows) == ("", ""):
        grid = pd.DataFrame([{
            "diagnostic_status": "blocked_insufficient_rows",
            "recommendation": "insufficient_rows",
            "reason": "Rating-backed rows or measured strength-index rows are required for baseline tuning diagnostics.",
        }])
        return grid, grid.copy()
    baseline = baseline_metrics or evaluate_projection_calibration(rows, data_source="baseline_tuning_current_baseline")["metrics"]
    baseline_scoreline = evaluate_scoreline_calibration(rows)["metrics"]
    grid_rows: list[dict[str, Any]] = []
    for params in tuning_grid(profile):
        projected = project_rows_with_candidate(rows, params)
        eval_result = evaluate_projection_calibration(projected, data_source="baseline_tuning_diagnostic")
        scoreline_result = evaluate_scoreline_calibration(projected)
        scoreline_metrics = scoreline_result["metrics"]
        metrics = eval_result["metrics"]
        record = {
            "diagnostic_status": "diagnostic_only",
            **params,
            "rows": metrics["row_count"],
            "wdl_log_loss": metrics["wdl_log_loss"],
            "brier_score": metrics["brier_score"],
            "accuracy": metrics.get("accuracy"),
            "total_goals_mae": metrics["total_goals_mae"],
            "over_2_5_brier": metrics["over_under_2_5_brier_score"],
            "btts_brier": scoreline_metrics.get("btts_brier_score"),
            "most_likely_score_hit_rate": metrics["most_likely_score_hit_rate"],
            "top_3_correct_score_hit_rate": scoreline_metrics.get("top_3_correct_score_hit_rate"),
            "top_5_correct_score_hit_rate": scoreline_metrics.get("top_5_correct_score_hit_rate"),
            "actual_score_rank_average": scoreline_metrics.get("actual_score_rank_average"),
            "mean_projected_total": metrics.get("mean_projected_total"),
            "mean_actual_total": metrics.get("mean_actual_total"),
            "predicted_actual_total_delta": _delta(metrics.get("mean_projected_total"), metrics.get("mean_actual_total")),
            "scoreline_diagnostic_labels": "; ".join(scoreline_result["labels"]),
        }
        record.update(_spread_calibration_metrics(projected))
        record["composite_score"] = _composite_score(record)
        record["wdl_log_loss_delta"] = _delta(record["wdl_log_loss"], baseline.get("wdl_log_loss"))
        record["total_goals_mae_delta"] = _delta(record["total_goals_mae"], baseline.get("total_goals_mae"))
        record["over_2_5_brier_delta"] = _delta(record["over_2_5_brier"], baseline.get("over_under_2_5_brier_score"))
        record["top_5_correct_score_hit_rate_delta"] = _delta(record["top_5_correct_score_hit_rate"], baseline_scoreline.get("top_5_correct_score_hit_rate"))
        record["actual_score_rank_average_delta"] = _delta(record["actual_score_rank_average"], baseline_scoreline.get("actual_score_rank_average"))
        record["recommendation"] = recommendation_for_candidate(record, baseline)
        record["candidate_label"] = scoreline_candidate_label(record, baseline)
        record["candidate_validation_status"] = candidate_validation_status(record, baseline)
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
            "baseline_metrics": baseline_metrics,
            "best_candidate_metrics": best.iloc[0].to_dict(),
        }
        candidate_path = output / "candidate_model_config.json"
        candidate_path.write_text(json.dumps(candidate, indent=2, default=str), encoding="utf-8")
        paths["candidate_model_config"] = candidate_path
        scoreline_candidate = dict(candidate)
        scoreline_candidate["config_type"] = "diagnostic_scoreline_candidate_model_config"
        scoreline_candidate["candidate_label"] = str(best.iloc[0].get("candidate_label", "needs_holdout_validation"))
        scoreline_candidate["warning"] = "Diagnostic-only scoreline/totals candidate. Production defaults remain unchanged."
        scoreline_candidate["source_calibration_run_id"] = str(Path(run_dir).name)
        scoreline_candidate_path = output / "candidate_scoreline_model_config.json"
        scoreline_candidate_path.write_text(json.dumps(scoreline_candidate, indent=2, default=str), encoding="utf-8")
        paths["candidate_scoreline_model_config"] = scoreline_candidate_path
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
        for key in ["candidate_model_config", "candidate_scoreline_model_config"]:
            config_path = paths.get(key)
            if config_path and Path(config_path).exists():
                payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
                payload["holdout"] = holdout_summary
                if holdout_paths.get("holdout_metrics") and Path(holdout_paths["holdout_metrics"]).exists():
                    payload["holdout_metrics"] = pd.read_csv(holdout_paths["holdout_metrics"]).to_dict(orient="records")
                Path(config_path).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
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


def scoreline_candidate_label(candidate: dict[str, Any], baseline: dict[str, Any]) -> str:
    rows = int(candidate.get("rows") or 0)
    if rows < 20:
        return "insufficient_rows"
    wdl_delta = _delta(candidate.get("wdl_log_loss"), baseline.get("wdl_log_loss"))
    totals_delta = _delta(candidate.get("total_goals_mae"), baseline.get("total_goals_mae"))
    ou_delta = _delta(candidate.get("over_2_5_brier"), baseline.get("over_under_2_5_brier_score"))
    top5_delta = float(candidate.get("top_5_correct_score_hit_rate_delta") or 0.0)
    rank_delta = float(candidate.get("actual_score_rank_average_delta") or 0.0)
    favorite_2plus_gap = abs(float(candidate.get("favorite_2plus_calibration_gap") or 0.0))
    if totals_delta < -0.03 and wdl_delta <= 0.015 and ou_delta <= 0.01:
        if top5_delta > 0 or rank_delta < 0:
            return "balanced_improvement"
        return "totals_improved_wdl_stable"
    if totals_delta < -0.03 and wdl_delta > 0.015:
        return "totals_improved_wdl_hurt"
    if favorite_2plus_gap < 0.08 and top5_delta >= 0:
        return "favorites_uncapped_improved"
    if top5_delta > 0.02 or rank_delta < -0.5:
        return "scoreline_spread_improved"
    if wdl_delta > 0.03:
        return "overfit_risk"
    if rows < 100:
        return "limited_holdout_confidence"
    return "keep_current_baseline"


def candidate_validation_status(candidate: dict[str, Any], baseline: dict[str, Any]) -> str:
    if float(candidate.get("mean_projected_total") or 0.0) <= 0:
        return "invalid_negative_or_missing_xg"
    if abs(float(candidate.get("predicted_actual_total_delta") or 0.0)) > 1.2:
        return "overfit_risk"
    wdl_delta = _delta(candidate.get("wdl_log_loss"), baseline.get("wdl_log_loss"))
    ou_delta = _delta(candidate.get("over_2_5_brier"), baseline.get("over_under_2_5_brier_score"))
    if ou_delta < -0.015 and wdl_delta > 0.025:
        return "totals_improved_wdl_hurt"
    if wdl_delta > 0.04:
        return "overfit_risk"
    return "valid_diagnostic_candidate"


def _spread_calibration_metrics(projected: pd.DataFrame) -> dict[str, Any]:
    if projected.empty:
        return {}
    favorite_rows = []
    underdog_rows = []
    band_rows = []
    for _, row in projected.iterrows():
        home_prob = float(row.get("home_win_prob") or 0.0)
        away_prob = float(row.get("away_win_prob") or 0.0)
        favorite_side = "home" if home_prob >= away_prob else "away"
        for side in ["home", "away"]:
            xg = float(row[f"{side}_xg"])
            goals = float(row[f"{side}_goals"])
            dist = score_distribution(xg, 1.0, max_goals=8) if side == "home" else score_distribution(1.0, xg, max_goals=8)
            goal_col = "home_goals" if side == "home" else "away_goals"
            prob_2plus = float(dist[dist[goal_col] >= 2]["probability"].sum())
            record = {"predicted_2plus": prob_2plus, "actual_2plus": float(goals >= 2)}
            if side == favorite_side:
                favorite_rows.append(record)
            else:
                underdog_rows.append(record)
            band = "3plus" if goals >= 3 else f"{int(goals)}"
            for label in ["0", "1", "2", "3plus"]:
                if label == "3plus":
                    predicted = float(dist[dist[goal_col] >= 3]["probability"].sum())
                else:
                    predicted = float(dist[dist[goal_col] == int(label)]["probability"].sum())
                band_rows.append({"band": label, "predicted": predicted, "actual": float(band == label)})
    return {
        "favorite_2plus_projected_rate": _mean([row["predicted_2plus"] for row in favorite_rows]),
        "favorite_2plus_actual_rate": _mean([row["actual_2plus"] for row in favorite_rows]),
        "favorite_2plus_calibration_gap": _mean([row["predicted_2plus"] - row["actual_2plus"] for row in favorite_rows]),
        "underdog_2plus_projected_rate": _mean([row["predicted_2plus"] for row in underdog_rows]),
        "underdog_2plus_actual_rate": _mean([row["actual_2plus"] for row in underdog_rows]),
        "underdog_2plus_calibration_gap": _mean([row["predicted_2plus"] - row["actual_2plus"] for row in underdog_rows]),
        **{
            f"goal_band_{label}_calibration_gap": _mean([row["predicted"] - row["actual"] for row in band_rows if row["band"] == label])
            for label in ["0", "1", "2", "3plus"]
        },
    }


def _mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


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
        "favorite_xg_spread_multiplier",
        "underdog_xg_floor",
        "underdog_xg_scale",
        "home_or_neutral_adjustment",
        "scoreline_dispersion_multiplier",
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
