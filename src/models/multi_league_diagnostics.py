from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.models.confidence_calibration import audit_confidence_calibration
from src.models.projection_profile_diagnostics import run_projection_profile_diagnostics


BUCKET_RE = re.compile(r"(High|Medium|Low): n=(\d+), total_mae=([0-9.]+), log_loss=([0-9.]+)")


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def _windows(data: pd.DataFrame, start_date: str, end_date: str, min_matches: int, monthly: bool) -> list[tuple[str, str, str]]:
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    custom = data[(data["date"] >= start) & (data["date"] <= end)]
    windows = [("custom", start.date().isoformat(), end.date().isoformat())]
    if monthly:
        for period, rows in custom.groupby(custom["date"].dt.to_period("M")):
            if len(rows) >= min_matches:
                month_start = rows["date"].min().date().isoformat()
                month_end = rows["date"].max().date().isoformat()
                windows.append((f"month_{period}", month_start, month_end))
    return windows


def _bucket_rows(summary: pd.DataFrame, league: str, league_name: str, window: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, result in summary.iterrows():
        text = str(result.get("confidence_bucket_summary", ""))
        for label, matches, total_mae, log_loss in BUCKET_RE.findall(text):
            rows.append({
                "league": league,
                "league_name": league_name,
                "window": window,
                "projection_profile": result["projection_profile"],
                "confidence_label": label,
                "matches": int(matches),
                "total_goals_mae": float(total_mae),
                "wdl_log_loss": float(log_loss),
            })
    return rows


def run_multi_league_profile_diagnostics(
    matches: pd.DataFrame | str | Path,
    start_date: str,
    end_date: str,
    profiles: list[str] | None = None,
    min_matches: int = 6,
    monthly: bool = False,
    output_dir: str | Path = "outputs/reports",
) -> dict[str, Any]:
    data = _load(matches)
    summaries = []
    confidence_rows: list[dict[str, Any]] = []
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for league, league_data in data.groupby("league", dropna=False):
        league = str(league)
        league_name = str(league_data["league_name"].dropna().iloc[0]) if "league_name" in league_data.columns and not league_data["league_name"].dropna().empty else league
        for window_name, window_start, window_end in _windows(league_data, start_date, end_date, min_matches, monthly):
            window_data = league_data[(league_data["date"] >= pd.to_datetime(window_start)) & (league_data["date"] <= pd.to_datetime(window_end))]
            if len(window_data) < min_matches:
                continue
            result = run_projection_profile_diagnostics(
                league_data,
                window_start,
                window_end,
                profiles=profiles,
                min_matches=min_matches,
                output_dir=output,
            )
            frame = result["results"].copy()
            frame.insert(0, "league", league)
            frame.insert(1, "league_name", league_name)
            frame.insert(2, "window", window_name)
            frame.insert(3, "window_start", window_start)
            frame.insert(4, "window_end", window_end)
            summaries.append(frame)
            confidence_rows.extend(_bucket_rows(frame, league, league_name, window_name))
    results = pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame()
    confidence = pd.DataFrame(confidence_rows)
    results_path = output / "multi_league_profile_diagnostics_results.csv"
    summary_path = output / "multi_league_profile_diagnostics_summary.md"
    confidence_path = output / "confidence_calibration_bucket_results.csv"
    results.to_csv(results_path, index=False)
    confidence.to_csv(confidence_path, index=False)
    calibration = audit_confidence_calibration(confidence, output_dir=output)
    report = write_multi_league_report(results, confidence, calibration, summary_path)
    return {
        "results": results,
        "confidence_buckets": confidence,
        "confidence_calibration": calibration,
        "report": report,
        "results_path": results_path,
        "summary_path": summary_path,
        "confidence_path": confidence_path,
    }


def _best_by(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    eligible = df[pd.to_numeric(df["matches"], errors="coerce").fillna(0) > 0].copy()
    if eligible.empty:
        return eligible
    return eligible.sort_values(metric).groupby(["league", "window"], as_index=False).head(1)


def _high_outperformed(confidence: pd.DataFrame) -> str:
    if confidence.empty:
        return "needs_more_data"
    verdicts = []
    for _, rows in confidence.groupby(["league", "window", "projection_profile"]):
        perf = rows.set_index("confidence_label")
        if "High" in perf.index and "Medium" in perf.index:
            high = perf.loc["High"]
            med = perf.loc["Medium"]
            verdicts.append(float(high["wdl_log_loss"]) <= float(med["wdl_log_loss"]) or float(high["total_goals_mae"]) <= float(med["total_goals_mae"]))
    if not verdicts:
        return "needs_more_data"
    return "yes" if all(verdicts) else "mixed"


def write_multi_league_report(results: pd.DataFrame, confidence: pd.DataFrame, calibration: dict[str, Any], output_path: str | Path) -> str:
    lines = [
        "# Multi-League Projection Profile Diagnostics",
        "",
        "Each league is calibrated separately. Proxy score adjustments remain disabled.",
        "",
        f"Confidence recommendation: `{calibration['recommended_confidence_language']}`",
        "",
        f"High confidence outperformed lower buckets: `{_high_outperformed(confidence)}`",
        "",
        "## Best W/D/L Profile By League",
        "",
    ]
    best_wdl = _best_by(results, "wdl_log_loss")
    if best_wdl.empty:
        lines.append("_No eligible rows._")
    else:
        lines.extend(_table(best_wdl, ["league", "window", "projection_profile", "matches", "wdl_log_loss", "brier_score"]))
    lines.extend(["", "## Best Totals Profile By League", ""])
    best_total = _best_by(results, "total_goals_mae")
    if best_total.empty:
        lines.append("_No eligible rows._")
    else:
        lines.extend(_table(best_total, ["league", "window", "projection_profile", "matches", "total_goals_mae", "over_under_2_5_accuracy"]))
    lines.append("")
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report


def _table(df: pd.DataFrame, columns: list[str]) -> list[str]:
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in df[columns].iterrows():
        values = [f"{row[col]:.4f}" if isinstance(row[col], float) else str(row[col]) for col in columns]
        lines.append("| " + " | ".join(values) + " |")
    return lines
