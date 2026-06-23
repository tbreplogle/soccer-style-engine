from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.models.current_baseline import current_baseline_expected_goals
from src.models.current_score_projection import project_current_match
from src.models.score_projection import _projection_from_xg


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    return data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)


def _log_loss(row: pd.Series) -> float:
    key = "home_win_prob" if row["home_goals"] > row["away_goals"] else "away_win_prob" if row["away_goals"] > row["home_goals"] else "draw_prob"
    return float(-np.log(max(1e-9, row[key])))


def _brier(row: pd.Series) -> float:
    actual = np.array([row["home_goals"] > row["away_goals"], row["home_goals"] == row["away_goals"], row["home_goals"] < row["away_goals"]], dtype=float)
    pred = np.array([row["home_win_prob"], row["draw_prob"], row["away_win_prob"]], dtype=float)
    return float(np.mean((pred - actual) ** 2))


def run_current_backtest(
    matches: pd.DataFrame | str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path = "outputs/reports",
) -> dict[str, pd.DataFrame | str]:
    data = _load(matches)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    window = data[(data["date"] >= pd.to_datetime(start_date)) & (data["date"] <= pd.to_datetime(end_date))].sort_values("date")
    rows = []
    for _, match in window.iterrows():
        as_of = match["date"].date().isoformat()
        home = match["home_team"]
        away = match["away_team"]
        projection = project_current_match(data, home, away, as_of).iloc[0].to_dict()
        baseline = current_baseline_expected_goals(data, home, away, as_of)
        base_probs = _projection_from_xg(float(baseline["home_xg_base"]), float(baseline["away_xg_base"]))
        rows.append({
            "match_id": match["match_id"],
            "date": as_of,
            "home_team": home,
            "away_team": away,
            "home_goals": match["home_goals"],
            "away_goals": match["away_goals"],
            "baseline_home_xg": baseline["home_xg_base"],
            "baseline_away_xg": baseline["away_xg_base"],
            "proxy_home_xg": projection["home_xg_final"],
            "proxy_away_xg": projection["away_xg_final"],
            "home_win_prob": projection["home_win_prob"],
            "draw_prob": projection["draw_prob"],
            "away_win_prob": projection["away_win_prob"],
            "over_2_5_prob": projection["over_2_5_prob"],
            "baseline_home_win_prob": base_probs["home_win_prob"],
            "baseline_draw_prob": base_probs["draw_prob"],
            "baseline_away_win_prob": base_probs["away_win_prob"],
        })
    results = pd.DataFrame(rows)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if results.empty:
        summary = "# Free Current Backtest Summary\n\nNo eligible matches.\n"
        results.to_csv(output / "free_current_backtest_results.csv", index=False)
        (output / "free_current_backtest_summary.md").write_text(summary, encoding="utf-8")
        return {"results": results, "summary": summary}
    results["home_goals_abs_error"] = (results["proxy_home_xg"] - results["home_goals"]).abs()
    results["away_goals_abs_error"] = (results["proxy_away_xg"] - results["away_goals"]).abs()
    results["total_goals_abs_error"] = ((results["proxy_home_xg"] + results["proxy_away_xg"]) - (results["home_goals"] + results["away_goals"])).abs()
    results["wdl_log_loss"] = results.apply(_log_loss, axis=1)
    results["brier_score"] = results.apply(_brier, axis=1)
    results["exact_score_hit"] = ((results["proxy_home_xg"].round().astype(int) == results["home_goals"]) & (results["proxy_away_xg"].round().astype(int) == results["away_goals"]))
    results["over_under_2_5_correct"] = ((results["over_2_5_prob"] >= 0.5) == ((results["home_goals"] + results["away_goals"]) > 2.5))
    baseline_total_mae = ((results["baseline_home_xg"] + results["baseline_away_xg"]) - (results["home_goals"] + results["away_goals"])).abs().mean()
    proxy_total_mae = results["total_goals_abs_error"].mean()
    summary = "\n".join([
        "# Free Current Backtest Summary",
        "",
        f"Matches: {len(results)}",
        f"Home goals MAE: {results['home_goals_abs_error'].mean():.3f}",
        f"Away goals MAE: {results['away_goals_abs_error'].mean():.3f}",
        f"Total goals MAE: {proxy_total_mae:.3f}",
        f"W/D/L log loss: {results['wdl_log_loss'].mean():.3f}",
        f"Brier score: {results['brier_score'].mean():.3f}",
        f"Exact score hit rate: {results['exact_score_hit'].mean():.3f}",
        f"Over/under 2.5 accuracy: {results['over_under_2_5_correct'].mean():.3f}",
        f"Proxy lift vs baseline total MAE: {baseline_total_mae - proxy_total_mae:.3f}",
        "",
        "Calibration summary: inspect probability bins in future larger samples.",
    ])
    results.to_csv(output / "free_current_backtest_results.csv", index=False)
    (output / "free_current_backtest_summary.md").write_text(summary, encoding="utf-8")
    return {"results": results, "summary": summary}
