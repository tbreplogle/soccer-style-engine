from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.models.multi_season_validation import PROFILES, run_multi_season_validation


ALLOWED_RECOMMENDATIONS = {
    "keep_current_defaults",
    "prefer_winner_probability_for_wdl",
    "prefer_market_anchored",
    "prefer_score_projection",
    "soften_confidence_language",
    "disable_confidence_labels",
    "needs_more_data",
}


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def _code_list(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _window(data: pd.DataFrame, seasons: list[str], output_dir: str | Path) -> pd.DataFrame:
    subset = data[data["season_code"].astype(str).isin(seasons)].copy()
    if subset.empty:
        return pd.DataFrame()
    result = run_multi_season_validation(
        subset,
        start_date=str(subset["date"].min().date()),
        end_date=str(subset["date"].max().date()),
        profiles=PROFILES,
        min_matches=1,
        output_dir=output_dir,
    )
    return result["results"]


def _profile_summary(results: pd.DataFrame, stage: str) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame(columns=["stage", "projection_profile", "matches", "wdl_log_loss", "brier_score", "total_goals_mae"])
    full = results[(results["window"].eq("full")) & (pd.to_numeric(results["matches"], errors="coerce").fillna(0) > 0)]
    if full.empty:
        return pd.DataFrame(columns=["stage", "projection_profile", "matches", "wdl_log_loss", "brier_score", "total_goals_mae"])
    summary = full.groupby("projection_profile", as_index=False).agg(
        matches=("matches", "sum"),
        wdl_log_loss=("wdl_log_loss", "mean"),
        brier_score=("brier_score", "mean"),
        total_goals_mae=("total_goals_mae", "mean"),
    )
    summary.insert(0, "stage", stage)
    return summary.sort_values(["wdl_log_loss", "brier_score", "total_goals_mae"])


def _select_profile(train_summary: pd.DataFrame, validation_summary: pd.DataFrame) -> tuple[str, str]:
    if train_summary.empty or validation_summary.empty:
        return "score_projection", "Not enough train/validation rows; retained conservative score projection default."
    merged = train_summary[["projection_profile", "wdl_log_loss"]].rename(columns={"wdl_log_loss": "train_log_loss"}).merge(
        validation_summary[["projection_profile", "wdl_log_loss", "total_goals_mae"]],
        on="projection_profile",
        how="inner",
    )
    if merged.empty:
        return "score_projection", "No shared train/validation profile metrics; retained conservative score projection default."
    merged["selection_score"] = merged["wdl_log_loss"] + 0.25 * merged["total_goals_mae"] + 0.15 * (merged["wdl_log_loss"] - merged["train_log_loss"]).abs()
    selected = str(merged.sort_values("selection_score").iloc[0]["projection_profile"])
    return selected, "Selected from train and validation metrics only; test-season metrics were not used for tuning."


def _recommend(selected: str, test_summary: pd.DataFrame, validation_summary: pd.DataFrame) -> tuple[str, str]:
    if validation_summary.empty or test_summary.empty:
        return "needs_more_data", "Insufficient validation or test rows."
    selected_test = test_summary[test_summary["projection_profile"].eq(selected)]
    if selected_test.empty:
        return "needs_more_data", "Selected profile has no test-season evaluation rows."
    best_test = test_summary.sort_values(["wdl_log_loss", "brier_score"]).iloc[0]
    selected_log_loss = float(selected_test.iloc[0]["wdl_log_loss"])
    best_log_loss = float(best_test["wdl_log_loss"])
    if selected_log_loss > best_log_loss + 0.08:
        return "soften_confidence_language", f"Selected profile trailed test best by {selected_log_loss - best_log_loss:.3f} log-loss."
    if selected == "winner_probability":
        return "prefer_winner_probability_for_wdl", "Winner-probability profile held up best through validation selection."
    if selected == "market_anchored":
        return "prefer_market_anchored", "Market-anchored profile held up best through validation selection."
    if selected == "score_projection":
        return "prefer_score_projection", "Score projection remained the selected default through validation."
    return "keep_current_defaults", "No stronger default change was supported."


def run_holdout_validation(
    matches: pd.DataFrame | str | Path,
    train_seasons: str | list[str],
    validation_season: str,
    test_season: str,
    output_dir: str | Path = "outputs/reports",
) -> dict[str, Any]:
    data = _load(matches)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    train_codes = _code_list(train_seasons)
    validation_code = str(validation_season)
    test_code = str(test_season)
    train_results = _window(data, train_codes, output)
    validation_results = _window(data, [validation_code], output)
    test_results = _window(data, [test_code], output)
    train_summary = _profile_summary(train_results, "train")
    validation_summary = _profile_summary(validation_results, "validation")
    test_summary = _profile_summary(test_results, "test")
    selected, reason = _select_profile(train_summary, validation_summary)
    recommendation, overfit_warning = _recommend(selected, test_summary, validation_summary)
    all_summary = pd.concat([train_summary, validation_summary, test_summary], ignore_index=True)
    test_row = test_summary[test_summary["projection_profile"].eq(selected)].to_dict("records")
    payload = {
        "selected_default_profile": selected,
        "selected_default_baseline": "blended" if selected != "market_anchored" else "market",
        "validation_reason": reason,
        "test_performance": test_row[0] if test_row else {},
        "train_vs_validation_vs_test_summary": all_summary,
        "overfit_warning": overfit_warning,
        "recommendation": recommendation if recommendation in ALLOWED_RECOMMENDATIONS else "needs_more_data",
    }
    report = write_holdout_validation_report(payload, output / "holdout_validation_summary.md")
    payload["report"] = report
    payload["summary_path"] = output / "holdout_validation_summary.md"
    return payload


def write_holdout_validation_report(payload: dict[str, Any], output_path: str | Path) -> str:
    summary = payload["train_vs_validation_vs_test_summary"]
    lines = [
        "# Holdout Validation Summary",
        "",
        f"Selected default profile: {payload['selected_default_profile']}",
        f"Selected default baseline: {payload['selected_default_baseline']}",
        f"Recommendation: {payload['recommendation']}",
        f"Validation reason: {payload['validation_reason']}",
        f"Overfit warning: {payload['overfit_warning']}",
        "",
        "Test-season data was not used to choose defaults.",
        "",
        "## Train vs Validation vs Test",
        "",
        _table(summary, ["stage", "projection_profile", "matches", "wdl_log_loss", "brier_score", "total_goals_mae"]),
        "",
    ]
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report


def _table(df: pd.DataFrame, columns: list[str], limit: int = 50) -> str:
    if df.empty:
        return "_No rows._"
    cols = [col for col in columns if col in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df[cols].head(limit).iterrows():
        values = []
        for col in cols:
            value = row[col]
            values.append(f"{float(value):.4f}" if isinstance(value, (float, np.floating)) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)
