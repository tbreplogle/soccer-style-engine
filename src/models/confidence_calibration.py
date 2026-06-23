from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


ALLOWED_CONFIDENCE_RECOMMENDATIONS = {
    "strong_confidence_labels_ok",
    "use_soft_confidence_language",
    "confidence_context_only",
    "needs_more_data",
}


def _score_bucket(label: str) -> int:
    return {"High": 3, "Medium": 2, "Low": 1}.get(label, 0)


def audit_confidence_calibration(bucket_results: pd.DataFrame | str | Path, output_dir: str | Path = "outputs/reports") -> dict[str, Any]:
    data = bucket_results.copy() if isinstance(bucket_results, pd.DataFrame) else pd.read_csv(bucket_results)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if data.empty or "confidence_label" not in data.columns:
        recommendation = "needs_more_data"
        summary = pd.DataFrame()
        warning = "No confidence bucket rows were available."
    else:
        data = data[pd.to_numeric(data["matches"], errors="coerce").fillna(0) > 0].copy()
        summary = data.groupby("confidence_label", as_index=False).agg(
            matches=("matches", "sum"),
            avg_total_goals_mae=("total_goals_mae", "mean"),
            avg_wdl_log_loss=("wdl_log_loss", "mean"),
            leagues=("league", "nunique") if "league" in data.columns else ("confidence_label", "count"),
        )
        label_perf = summary.set_index("confidence_label")
        has_high = "High" in label_perf.index
        has_medium = "Medium" in label_perf.index
        has_low = "Low" in label_perf.index
        total_matches = int(summary["matches"].sum()) if not summary.empty else 0
        high_better_log = has_high and has_medium and float(label_perf.loc["High", "avg_wdl_log_loss"]) <= float(label_perf.loc["Medium", "avg_wdl_log_loss"])
        high_better_total = has_high and has_medium and float(label_perf.loc["High", "avg_total_goals_mae"]) <= float(label_perf.loc["Medium", "avg_total_goals_mae"])
        by_league = []
        if "league" in data.columns:
            for league, rows in data.groupby("league"):
                perf = rows.groupby("confidence_label", as_index=True).agg(
                    wdl_log_loss=("wdl_log_loss", "mean"),
                    total_goals_mae=("total_goals_mae", "mean"),
                )
                if "High" in perf.index and "Medium" in perf.index:
                    by_league.append({
                        "league": league,
                        "high_log_loss_better": float(perf.loc["High", "wdl_log_loss"]) <= float(perf.loc["Medium", "wdl_log_loss"]),
                        "high_total_mae_better": float(perf.loc["High", "total_goals_mae"]) <= float(perf.loc["Medium", "total_goals_mae"]),
                    })
        consistent = bool(by_league) and all(item["high_log_loss_better"] or item["high_total_mae_better"] for item in by_league)
        if total_matches < 200 or not has_high or not (has_medium or has_low):
            recommendation = "needs_more_data"
            warning = "Confidence buckets do not have enough populated comparison rows."
        elif high_better_log and high_better_total and consistent:
            recommendation = "strong_confidence_labels_ok"
            warning = "High confidence performed better than lower buckets across the available checks."
        elif high_better_log or high_better_total:
            recommendation = "use_soft_confidence_language"
            warning = "High confidence helped on some metrics but was not consistently superior."
        else:
            recommendation = "confidence_context_only"
            warning = "High confidence did not consistently outperform lower buckets."
    report_path = output / "confidence_calibration_summary.md"
    report = write_confidence_calibration_report(summary, warning, recommendation, report_path)
    return {
        "confidence_bucket_summary": summary,
        "confidence_reliability_warning": warning,
        "recommended_confidence_language": recommendation,
        "report": report,
        "report_path": report_path,
    }


def write_confidence_calibration_report(summary: pd.DataFrame, warning: str, recommendation: str, output_path: str | Path) -> str:
    lines = [
        "# Confidence Calibration Summary",
        "",
        f"Recommended confidence language: `{recommendation}`",
        "",
        warning,
        "",
        "## Buckets",
        "",
    ]
    if summary.empty:
        lines.append("_No confidence bucket rows._")
    else:
        columns = list(summary.columns)
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
        for _, row in summary.iterrows():
            values = [f"{row[col]:.4f}" if isinstance(row[col], float) else str(row[col]) for col in columns]
            lines.append("| " + " | ".join(values) + " |")
    lines.append("")
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report


def confidence_correlation_summary(bucket_results: pd.DataFrame) -> dict[str, float | None]:
    data = bucket_results.copy()
    if data.empty:
        return {"log_loss_corr": None, "total_mae_corr": None}
    data["confidence_rank"] = data["confidence_label"].map(_score_bucket)
    return {
        "log_loss_corr": float(data["confidence_rank"].corr(pd.to_numeric(data["wdl_log_loss"], errors="coerce"))),
        "total_mae_corr": float(data["confidence_rank"].corr(pd.to_numeric(data["total_goals_mae"], errors="coerce"))),
    }
