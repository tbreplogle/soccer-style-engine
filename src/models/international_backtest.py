from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.models.international_projection import project_international_match


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def _log_loss(row: dict[str, Any]) -> float:
    key = "team_a_win_prob" if row["team_a_goals"] > row["team_b_goals"] else "team_b_win_prob" if row["team_b_goals"] > row["team_a_goals"] else "draw_prob"
    return float(-np.log(max(1e-9, float(row[key]))))


def _brier(row: dict[str, Any]) -> float:
    actual = np.array([row["team_a_goals"] > row["team_b_goals"], row["team_a_goals"] == row["team_b_goals"], row["team_a_goals"] < row["team_b_goals"]], dtype=float)
    pred = np.array([row["team_a_win_prob"], row["draw_prob"], row["team_b_win_prob"]], dtype=float)
    return float(np.mean((pred - actual) ** 2))


def run_international_backtest(
    matches: pd.DataFrame | str | Path,
    start_date: str,
    end_date: str,
    competition_name: str | None = None,
    competition_id: str | int | None = None,
    season_id: str | int | None = None,
    output_dir: str | Path = "outputs/reports",
    min_prior_matches: int = 5,
) -> dict[str, Any]:
    data = _load(matches)
    if competition_name:
        data = data[data["competition_name"].astype(str).str.contains(competition_name, case=False, na=False)].copy()
    if competition_id is not None:
        data = data[data["competition_id"].astype(str).eq(str(competition_id))].copy()
    if season_id is not None:
        data = data[data["season_id"].astype(str).eq(str(season_id))].copy()
    window = data[(data["date"] >= pd.to_datetime(start_date)) & (data["date"] <= pd.to_datetime(end_date))].sort_values("date")
    rows = []
    for _, match in window.iterrows():
        prior = data[data["date"] < match["date"]]
        team_a_prior = prior[(prior["home_team"].eq(match["home_team"])) | (prior["away_team"].eq(match["home_team"]))]
        team_b_prior = prior[(prior["home_team"].eq(match["away_team"])) | (prior["away_team"].eq(match["away_team"]))]
        sparse = len(team_a_prior) < min_prior_matches or len(team_b_prior) < min_prior_matches
        projection = project_international_match(
            data,
            match["home_team"],
            match["away_team"],
            match["date"].date().isoformat(),
            neutral_site=match.get("neutral_site", "unknown"),
            competition_context=str(match.get("competition_name", "")),
        ).iloc[0]
        rows.append({
            "match_id": match["match_id"],
            "date": match["date"].date().isoformat(),
            "team_a": match["home_team"],
            "team_b": match["away_team"],
            "team_a_goals": float(match["home_score"]),
            "team_b_goals": float(match["away_score"]),
            "team_a_xg": float(projection["team_a_xg_final"]),
            "team_b_xg": float(projection["team_b_xg_final"]),
            "team_a_win_prob": float(projection["team_a_win_prob"]),
            "draw_prob": float(projection["draw_prob"]),
            "team_b_win_prob": float(projection["team_b_win_prob"]),
            "over_2_5_prob": float(projection["over_2_5_prob"]),
            "confidence_label": projection["confidence_label"],
            "sparse_sample_warning": sparse,
        })
    results = pd.DataFrame(rows)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results_path = output / "international_backtest_results.csv"
    summary_path = output / "international_backtest_summary.md"
    results.to_csv(results_path, index=False)
    summary = summarize_international_backtest(results, summary_path)
    return {"results": results, "summary": summary, "results_path": results_path, "summary_path": summary_path}


def summarize_international_backtest(results: pd.DataFrame, output_path: str | Path) -> str:
    if results.empty:
        report = "# International Backtest Summary\n\nNo eligible matches.\n"
        Path(output_path).write_text(report, encoding="utf-8")
        return report
    rows = results.to_dict("records")
    home_mae = float(np.mean(abs(results["team_a_xg"] - results["team_a_goals"])))
    away_mae = float(np.mean(abs(results["team_b_xg"] - results["team_b_goals"])))
    total_mae = float(np.mean(abs((results["team_a_xg"] + results["team_b_xg"]) - (results["team_a_goals"] + results["team_b_goals"]))))
    exact = float(np.mean((results["team_a_xg"].round() == results["team_a_goals"]) & (results["team_b_xg"].round() == results["team_b_goals"])))
    ou = float(np.mean((results["over_2_5_prob"] >= 0.5) == ((results["team_a_goals"] + results["team_b_goals"]) > 2.5)))
    sparse_rate = float(results["sparse_sample_warning"].mean())
    bucket_parts = []
    for label, bucket in results.groupby("confidence_label"):
        bucket_total_mae = float(np.mean(abs((bucket["team_a_xg"] + bucket["team_b_xg"]) - (bucket["team_a_goals"] + bucket["team_b_goals"]))))
        bucket_parts.append(f"{label}: n={len(bucket)}, total_mae={bucket_total_mae:.3f}")
    report = "\n".join([
        "# International Backtest Summary",
        "",
        f"Matches evaluated: {len(results)}",
        f"Team A goals MAE: {home_mae:.4f}",
        f"Team B goals MAE: {away_mae:.4f}",
        f"Total goals MAE: {total_mae:.4f}",
        f"W/D/L log loss: {np.mean([_log_loss(row) for row in rows]):.4f}",
        f"Brier score: {np.mean([_brier(row) for row in rows]):.4f}",
        f"Exact score hit rate: {exact:.4f}",
        f"Over/under 2.5 accuracy: {ou:.4f}",
        f"Sparse-sample warning rate: {sparse_rate:.4f}",
        "Confidence buckets: " + "; ".join(bucket_parts),
        "",
    ])
    Path(output_path).write_text(report, encoding="utf-8")
    return report

