from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.analysis.poisson_output import excel_safe_score_label
from src.models.score_projection import score_distribution


TEAM_GOAL_BANDS = ("0", "1", "2", "3+")
TOTAL_GOAL_BANDS = ("0-1", "2", "3", "4+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id(created_at: str) -> str:
    stamp = created_at[:19].replace("-", "").replace("T", "_").replace(":", "")
    suffix = hashlib.sha1(created_at.encode("utf-8")).hexdigest()[:8]
    return f"scoreline_diag_{stamp}_{suffix}"


def _number(row: pd.Series, names: list[str], default: float = np.nan) -> float:
    for name in names:
        if name in row and not pd.isna(row[name]):
            try:
                return float(row[name])
            except (TypeError, ValueError):
                continue
    return default


def _text(row: pd.Series, names: list[str], default: str = "") -> str:
    for name in names:
        if name in row and not pd.isna(row[name]):
            return str(row[name])
    return default


def _clean_score(value: Any) -> str:
    return str(value or "").replace(" ", "").replace(" - ", "-")


def _goal_band(goals: int | float) -> str:
    goals_int = int(goals)
    if goals_int >= 3:
        return "3+"
    return str(goals_int)


def _total_band(goals: int | float) -> str:
    goals_int = int(goals)
    if goals_int <= 1:
        return "0-1"
    if goals_int >= 4:
        return "4+"
    return str(goals_int)


def _matrix_for(home_xg: float, away_xg: float, max_goals: int) -> pd.DataFrame:
    matrix = score_distribution(max(0.0, home_xg), max(0.0, away_xg), max_goals=max_goals)
    total = float(matrix["probability"].sum())
    if total > 0:
        matrix["probability"] = matrix["probability"] / total
    matrix["score_label"] = matrix.apply(lambda row: excel_safe_score_label(row["home_goals"], row["away_goals"]), axis=1)
    return matrix.sort_values("probability", ascending=False).reset_index(drop=True)


def scoreline_rankings(rows: pd.DataFrame, *, max_goals: int = 8) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for index, row in rows.reset_index(drop=True).iterrows():
        home_xg = _number(row, ["home_xg", "projected_home_xg", "team_a_xg_final"])
        away_xg = _number(row, ["away_xg", "projected_away_xg", "team_b_xg_final"])
        home_goals = _number(row, ["home_goals", "actual_home_goals"])
        away_goals = _number(row, ["away_goals", "actual_away_goals"])
        if pd.isna(home_xg) or pd.isna(away_xg) or pd.isna(home_goals) or pd.isna(away_goals):
            continue
        matrix = _matrix_for(home_xg, away_xg, max_goals=max_goals)
        actual_label = excel_safe_score_label(home_goals, away_goals)
        actual_clean = _clean_score(actual_label)
        matrix["rank"] = np.arange(1, len(matrix) + 1)
        hit = matrix[matrix["score_label"].apply(_clean_score).eq(actual_clean)]
        if hit.empty:
            actual_rank = None
            actual_probability = 0.0
        else:
            actual_rank = int(hit.iloc[0]["rank"])
            actual_probability = float(hit.iloc[0]["probability"])
        top_scores = matrix.head(5)
        top_3 = [_clean_score(value) for value in top_scores.head(3)["score_label"].tolist()]
        top_5 = [_clean_score(value) for value in top_scores["score_label"].tolist()]
        records.append({
            "match_index": index,
            "fixture_date": _text(row, ["fixture_date", "match_date", "date"]),
            "home_team": _text(row, ["home_team", "team_a"]),
            "away_team": _text(row, ["away_team", "team_b"]),
            "projected_home_xg": home_xg,
            "projected_away_xg": away_xg,
            "projected_total": home_xg + away_xg,
            "actual_home_goals": int(home_goals),
            "actual_away_goals": int(away_goals),
            "actual_total": int(home_goals + away_goals),
            "most_likely_exact_score": matrix.iloc[0]["score_label"],
            "most_likely_exact_score_probability": float(matrix.iloc[0]["probability"]),
            "top_3_correct_scores": " | ".join(top_scores.head(3)["score_label"].astype(str)),
            "top_5_correct_scores": " | ".join(top_scores["score_label"].astype(str)),
            "actual_score": actual_label,
            "exact_score_hit": _clean_score(matrix.iloc[0]["score_label"]) == actual_clean,
            "top_3_score_hit": actual_clean in top_3,
            "top_5_score_hit": actual_clean in top_5,
            "actual_score_rank": actual_rank,
            "actual_score_probability": actual_probability,
            "home_win_probability": _number(row, ["home_win_prob", "home_win_probability", "team_a_win_prob"], 0.0),
            "draw_probability": _number(row, ["draw_prob", "draw_probability"], 0.0),
            "away_win_probability": _number(row, ["away_win_prob", "away_win_probability", "team_b_win_prob"], 0.0),
            "over_2_5_probability": _number(row, ["over_2_5_prob", "over_2_5_probability"], np.nan),
            "btts_probability": _number(row, ["btts_prob", "btts_yes_probability"], np.nan),
        })
    return pd.DataFrame(records)


def _team_goal_band_calibration(rankings: pd.DataFrame, *, max_goals: int = 8) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in rankings.iterrows():
        matrix = _matrix_for(float(row["projected_home_xg"]), float(row["projected_away_xg"]), max_goals=max_goals)
        for side, goal_col, actual in [
            ("home", "home_goals", int(row["actual_home_goals"])),
            ("away", "away_goals", int(row["actual_away_goals"])),
        ]:
            for band in TEAM_GOAL_BANDS:
                if band == "3+":
                    prob = float(matrix[matrix[goal_col] >= 3]["probability"].sum())
                else:
                    prob = float(matrix[matrix[goal_col] == int(band)]["probability"].sum())
                rows.append({"side": side, "goal_band": band, "projected_probability": prob, "actual": float(_goal_band(actual) == band)})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["side", "goal_band", "rows", "average_probability", "actual_rate", "calibration_gap"])
    grouped = frame.groupby(["side", "goal_band"], observed=False)
    return grouped.agg(
        rows=("actual", "size"),
        average_probability=("projected_probability", "mean"),
        actual_rate=("actual", "mean"),
    ).reset_index().assign(calibration_gap=lambda data: data["average_probability"] - data["actual_rate"])


def _total_goal_band_calibration(rankings: pd.DataFrame, *, max_goals: int = 8) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in rankings.iterrows():
        matrix = _matrix_for(float(row["projected_home_xg"]), float(row["projected_away_xg"]), max_goals=max_goals)
        total = matrix["home_goals"] + matrix["away_goals"]
        actual = int(row["actual_total"])
        for band in TOTAL_GOAL_BANDS:
            if band == "0-1":
                prob = float(matrix[total <= 1]["probability"].sum())
            elif band == "4+":
                prob = float(matrix[total >= 4]["probability"].sum())
            else:
                prob = float(matrix[total == int(band)]["probability"].sum())
            rows.append({"total_goal_band": band, "projected_probability": prob, "actual": float(_total_band(actual) == band)})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["total_goal_band", "rows", "average_probability", "actual_rate", "calibration_gap"])
    grouped = frame.groupby("total_goal_band", observed=False)
    return grouped.agg(
        rows=("actual", "size"),
        average_probability=("projected_probability", "mean"),
        actual_rate=("actual", "mean"),
    ).reset_index().assign(calibration_gap=lambda data: data["average_probability"] - data["actual_rate"])


def diagnostic_labels(metrics: dict[str, Any], rankings: pd.DataFrame, *, min_rows: int = 20) -> list[str]:
    labels: list[str] = []
    rows = int(metrics.get("row_count") or 0)
    if rows < min_rows:
        labels.append("insufficient_rows")
    total_gap = float(metrics.get("mean_projected_total") or 0.0) - float(metrics.get("mean_actual_total") or 0.0)
    if total_gap < -0.15:
        labels.append("totals_too_low")
    elif total_gap > 0.15:
        labels.append("totals_too_high")
    if metrics.get("top_5_correct_score_hit_rate") is not None and float(metrics["top_5_correct_score_hit_rate"]) < 0.28:
        labels.extend(["scorelines_too_compressed", "needs_more_goal_spread"])
    rank_average = metrics.get("actual_score_rank_average")
    if rank_average is not None and float(rank_average) > 8.0:
        labels.append("scorelines_too_compressed")
    draw_gap = float(metrics.get("draw_average_probability") or 0.0) - float(metrics.get("draw_actual_rate") or 0.0)
    if draw_gap > 0.06:
        labels.append("draw_cluster_too_high")
    if not rankings.empty:
        favorites = rankings[rankings[["home_win_probability", "away_win_probability"]].max(axis=1) >= 0.48]
        if not favorites.empty:
            favorite_goal_error = []
            underdog_goal_error = []
            for _, row in favorites.iterrows():
                if float(row["home_win_probability"]) >= float(row["away_win_probability"]):
                    favorite_goal_error.append(float(row["actual_home_goals"]) - float(row["projected_home_xg"]))
                    underdog_goal_error.append(float(row["actual_away_goals"]) - float(row["projected_away_xg"]))
                else:
                    favorite_goal_error.append(float(row["actual_away_goals"]) - float(row["projected_away_xg"]))
                    underdog_goal_error.append(float(row["actual_home_goals"]) - float(row["projected_home_xg"]))
            if float(np.mean(favorite_goal_error)) > 0.25:
                labels.append("favorites_too_capped")
            if float(np.mean(underdog_goal_error)) < -0.25:
                labels.append("underdogs_too_high")
    return list(dict.fromkeys(labels)) or ["continue_monitoring"]


def evaluate_scoreline_calibration(rows: pd.DataFrame, *, max_goals: int = 8, min_rows: int = 20) -> dict[str, Any]:
    rankings = scoreline_rankings(rows, max_goals=max_goals)
    if rankings.empty:
        metrics = {
            "row_count": 0,
            "actual_score_hit_rate": None,
            "top_3_correct_score_hit_rate": None,
            "top_5_correct_score_hit_rate": None,
            "actual_score_rank_average": None,
            "average_actual_score_probability": None,
            "total_goals_mae": None,
            "home_goals_mae": None,
            "away_goals_mae": None,
            "over_under_2_5_brier_score": None,
            "btts_brier_score": None,
        }
        return {
            "metrics": metrics,
            "labels": ["insufficient_rows"],
            "scoreline_metrics": pd.DataFrame([metrics]),
            "scoreline_topk_metrics": pd.DataFrame(),
            "team_goal_band_calibration": pd.DataFrame(),
            "total_goal_band_calibration": pd.DataFrame(),
            "actual_score_rankings": rankings,
        }
    rankings = rankings.copy()
    rankings["actual_over_2_5"] = rankings["actual_total"] > 2.5
    rankings["actual_btts"] = (rankings["actual_home_goals"] > 0) & (rankings["actual_away_goals"] > 0)
    rankings["over_2_5_probability"] = pd.to_numeric(rankings["over_2_5_probability"], errors="coerce").fillna(0.5)
    rankings["btts_probability"] = pd.to_numeric(rankings["btts_probability"], errors="coerce").fillna(0.5)
    metrics = {
        "row_count": int(len(rankings)),
        "actual_score_hit_rate": float(rankings["exact_score_hit"].mean()),
        "top_3_correct_score_hit_rate": float(rankings["top_3_score_hit"].mean()),
        "top_5_correct_score_hit_rate": float(rankings["top_5_score_hit"].mean()),
        "actual_score_rank_average": float(pd.to_numeric(rankings["actual_score_rank"], errors="coerce").dropna().mean()) if rankings["actual_score_rank"].notna().any() else None,
        "average_actual_score_probability": float(rankings["actual_score_probability"].mean()),
        "total_goals_mae": float((rankings["projected_total"] - rankings["actual_total"]).abs().mean()),
        "home_goals_mae": float((rankings["projected_home_xg"] - rankings["actual_home_goals"]).abs().mean()),
        "away_goals_mae": float((rankings["projected_away_xg"] - rankings["actual_away_goals"]).abs().mean()),
        "over_under_2_5_brier_score": float(((rankings["over_2_5_probability"] - rankings["actual_over_2_5"].astype(float)) ** 2).mean()),
        "btts_brier_score": float(((rankings["btts_probability"] - rankings["actual_btts"].astype(float)) ** 2).mean()),
        "mean_projected_total": float(rankings["projected_total"].mean()),
        "mean_actual_total": float(rankings["actual_total"].mean()),
        "draw_average_probability": float(rankings["draw_probability"].mean()),
        "draw_actual_rate": float((rankings["actual_home_goals"] == rankings["actual_away_goals"]).mean()),
    }
    topk = pd.DataFrame([
        {"k": 1, "hit_rate": metrics["actual_score_hit_rate"]},
        {"k": 3, "hit_rate": metrics["top_3_correct_score_hit_rate"]},
        {"k": 5, "hit_rate": metrics["top_5_correct_score_hit_rate"]},
    ])
    labels = diagnostic_labels(metrics, rankings, min_rows=min_rows)
    return {
        "metrics": metrics,
        "labels": labels,
        "scoreline_metrics": pd.DataFrame([{**metrics, "diagnostic_labels": "; ".join(labels)}]),
        "scoreline_topk_metrics": topk,
        "team_goal_band_calibration": _team_goal_band_calibration(rankings, max_goals=max_goals),
        "total_goal_band_calibration": _total_goal_band_calibration(rankings, max_goals=max_goals),
        "actual_score_rankings": rankings,
    }


def write_scoreline_diagnostics(
    rows: pd.DataFrame,
    *,
    as_of_date: str,
    output_dir: str | Path = "outputs/calibration",
    run_id: str | None = None,
    max_goals: int = 8,
    min_rows: int = 20,
) -> dict[str, Any]:
    created_at = _now_iso()
    diag_run_id = run_id or _run_id(created_at)
    output = Path(output_dir) / as_of_date / "scoreline_diagnostics" / diag_run_id
    output.mkdir(parents=True, exist_ok=True)
    result = evaluate_scoreline_calibration(rows, max_goals=max_goals, min_rows=min_rows)
    paths = {
        "scoreline_diagnostics_summary": output / "scoreline_diagnostics_summary.md",
        "scoreline_metrics": output / "scoreline_metrics.csv",
        "scoreline_topk_metrics": output / "scoreline_topk_metrics.csv",
        "team_goal_band_calibration": output / "team_goal_band_calibration.csv",
        "total_goal_band_calibration": output / "total_goal_band_calibration.csv",
        "actual_score_rankings": output / "actual_score_rankings.csv",
        "manifest": output / "scoreline_diagnostics_manifest.json",
    }
    for key in [
        "scoreline_metrics",
        "scoreline_topk_metrics",
        "team_goal_band_calibration",
        "total_goal_band_calibration",
        "actual_score_rankings",
    ]:
        result[key].to_csv(paths[key], index=False)
    manifest = {
        "run_id": diag_run_id,
        "entry_type": "scoreline_diagnostics",
        "run_date": as_of_date,
        "generated_at": created_at,
        "status": "diagnostic_only",
        "diagnostic_only": True,
        "production_defaults_changed": False,
        "metrics": result["metrics"],
        "diagnostic_labels": result["labels"],
        "guardrails": {
            "current_statsbomb_live_data_used": False,
            "proxy_adjustments_enabled": False,
            "betting_recommendations": False,
        },
        "output_paths": {key: str(path) for key, path in paths.items()},
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    paths["scoreline_diagnostics_summary"].write_text(_summary_markdown(manifest, result), encoding="utf-8")
    return {**result, "manifest": manifest, "paths": {key: str(path) for key, path in paths.items()}, "run_dir": output}


def _summary_markdown(manifest: dict[str, Any], result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    labels = result["labels"]
    lines = [
        "# Scoreline And Totals Diagnostics",
        "",
        "- Diagnostic-only calibration report.",
        "- Production projection defaults are unchanged.",
        "- Exact scores are naturally low-probability outcomes.",
        "",
        "## Metrics",
        "",
        f"- Rows: `{metrics.get('row_count')}`",
        f"- Exact score hit rate: `{metrics.get('actual_score_hit_rate')}`",
        f"- Top 3 correct score hit rate: `{metrics.get('top_3_correct_score_hit_rate')}`",
        f"- Top 5 correct score hit rate: `{metrics.get('top_5_correct_score_hit_rate')}`",
        f"- Average actual score rank: `{metrics.get('actual_score_rank_average')}`",
        f"- Average actual score probability: `{metrics.get('average_actual_score_probability')}`",
        f"- Total goals MAE: `{metrics.get('total_goals_mae')}`",
        f"- O/U 2.5 Brier: `{metrics.get('over_under_2_5_brier_score')}`",
        f"- BTTS Brier: `{metrics.get('btts_brier_score')}`",
        "",
        "## Diagnostic Labels",
        "",
        *[f"- `{label}`" for label in labels],
        "",
        "## Interpretation",
        "",
        f"- Scorelines too compressed: `{'scorelines_too_compressed' in labels}`",
        f"- Projected totals too low: `{'totals_too_low' in labels}`",
        "- Top 3/top 5 coverage should be read as distribution coverage, not a hard exact-score forecast.",
        "- Candidate tuning dimensions to test next: baseline total goals, total-goals adjustment, rating spread scale, favorite spread, underdog floor, and draw dampening.",
    ]
    return "\n".join(lines)

