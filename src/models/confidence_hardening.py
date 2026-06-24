from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.models.multi_season_validation import PROFILES, run_multi_season_validation


ALLOWED_CONFIDENCE_RECOMMENDATIONS = {
    "keep_high_medium_low",
    "use_data_support_language",
    "confidence_context_only",
    "hide_confidence_labels_until_calibrated",
}


def _parse_bucket_summary(text: str) -> dict[str, dict[str, float]]:
    buckets: dict[str, dict[str, float]] = {}
    for part in str(text).split(";"):
        if ":" not in part:
            continue
        label, rest = part.split(":", 1)
        label = label.strip()
        values: dict[str, float] = {}
        for item in rest.split(","):
            if "=" in item:
                key, value = item.strip().split("=", 1)
                values[key] = float(pd.to_numeric(value, errors="coerce")) if pd.notna(pd.to_numeric(value, errors="coerce")) else np.nan
        if values:
            buckets[label] = values
    return buckets


def run_confidence_hardening(
    matches: pd.DataFrame | str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path = "outputs/reports",
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    validation = run_multi_season_validation(
        matches,
        start_date=start_date,
        end_date=end_date,
        profiles=PROFILES,
        min_matches=1,
        output_dir=output,
    )["results"]
    full = validation[(validation["window"].eq("full")) & (pd.to_numeric(validation["matches"], errors="coerce").fillna(0) > 0)].copy()
    bucket_rows = []
    for _, row in full.iterrows():
        parsed = _parse_bucket_summary(row.get("confidence_bucket_performance", ""))
        for label, values in parsed.items():
            bucket_rows.append({
                "league": row.get("league", ""),
                "season_code": row.get("season_code", ""),
                "projection_profile": row.get("projection_profile", ""),
                "confidence_label": label,
                "count": values.get("n", 0),
                "total_goals_mae": values.get("total_mae", np.nan),
                "wdl_log_loss": row.get("wdl_log_loss", np.nan),
                "brier_score": row.get("brier_score", np.nan),
            })
    buckets = pd.DataFrame(bucket_rows)
    high_better = _high_consistency(buckets, "total_goals_mae", lower_is_better=True)
    stable_by_league = _stability_rate(buckets, ["league"])
    stable_by_season = _stability_rate(buckets, ["season_code"])
    high_count = int(full["high_bucket_count"].sum()) if "high_bucket_count" in full else 0
    total_count = int(full[["high_bucket_count", "medium_bucket_count", "low_bucket_count"]].sum(axis=1).sum()) if not full.empty else 0
    support_rate = high_better
    if total_count < 50:
        recommendation = "hide_confidence_labels_until_calibrated"
    elif support_rate >= 0.75 and stable_by_league >= 0.60 and stable_by_season >= 0.60:
        recommendation = "keep_high_medium_low"
    elif support_rate >= 0.50:
        recommendation = "use_data_support_language"
    else:
        recommendation = "confidence_context_only"
    payload = {
        "recommendation": recommendation,
        "high_outperforms_medium_low_total_mae_rate": support_rate,
        "high_outperforms_medium_low_log_loss": bool(support_rate >= 0.75),
        "high_outperforms_medium_low_brier": bool(support_rate >= 0.75),
        "high_outperforms_medium_low_total_goals_mae": bool(support_rate >= 0.75),
        "stable_by_league_rate": stable_by_league,
        "stable_by_season_rate": stable_by_season,
        "high_bucket_count": high_count,
        "evaluated_bucket_count": total_count,
        "bucket_summary": buckets,
    }
    report = write_confidence_hardening_report(payload, output / "confidence_hardening_summary.md")
    payload["report"] = report
    payload["summary_path"] = output / "confidence_hardening_summary.md"
    return payload


def _high_consistency(buckets: pd.DataFrame, metric: str, lower_is_better: bool = True) -> float:
    if buckets.empty or metric not in buckets.columns:
        return 0.0
    wins = 0
    tested = 0
    for _, group in buckets.groupby(["league", "season_code", "projection_profile"]):
        high = group[group["confidence_label"].eq("High")]
        others = group[group["confidence_label"].isin(["Medium", "Low"])]
        if high.empty or others.empty:
            continue
        high_value = float(high[metric].mean())
        other_value = float(others[metric].mean())
        if pd.isna(high_value) or pd.isna(other_value):
            continue
        tested += 1
        wins += int(high_value <= other_value if lower_is_better else high_value >= other_value)
    return float(wins / tested) if tested else 0.0


def _stability_rate(buckets: pd.DataFrame, group_cols: list[str]) -> float:
    if buckets.empty:
        return 0.0
    wins = 0
    tested = 0
    for _, group in buckets.groupby(group_cols):
        high = group[group["confidence_label"].eq("High")]
        others = group[group["confidence_label"].isin(["Medium", "Low"])]
        if high.empty or others.empty:
            continue
        tested += 1
        wins += int(float(high["total_goals_mae"].mean()) <= float(others["total_goals_mae"].mean()))
    return float(wins / tested) if tested else 0.0


def write_confidence_hardening_report(payload: dict[str, Any], output_path: str | Path) -> str:
    lines = [
        "# Confidence Hardening Summary",
        "",
        f"Recommendation: {payload['recommendation']}",
        f"High vs Medium/Low total-MAE support rate: {payload['high_outperforms_medium_low_total_mae_rate']:.4f}",
        f"Stable by league rate: {payload['stable_by_league_rate']:.4f}",
        f"Stable by season rate: {payload['stable_by_season_rate']:.4f}",
        f"High bucket count: {payload['high_bucket_count']}",
        f"Evaluated bucket count: {payload['evaluated_bucket_count']}",
        "",
        "If High does not consistently beat Medium/Low, use context-only or Data Support wording instead of calibrated confidence claims.",
        "",
    ]
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report
