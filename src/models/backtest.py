from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.config import REPORTS_DIR, TEAM_MATCH_STYLE_LOG_PATH
from src.models.baseline_strength import baseline_expected_goals
from src.models.score_projection import _projection_from_xg, project_match


def _load_log(style_log: pd.DataFrame | str | Path | None = None) -> pd.DataFrame:
    if style_log is None:
        return pd.read_csv(TEAM_MATCH_STYLE_LOG_PATH)
    if isinstance(style_log, pd.DataFrame):
        return style_log.copy()
    return pd.read_csv(style_log)


def _log_loss(row: pd.Series) -> float:
    actual = "home_win_prob" if row["home_goals"] > row["away_goals"] else "away_win_prob" if row["away_goals"] > row["home_goals"] else "draw_prob"
    return float(-np.log(max(1e-9, row[actual])))


def _brier(row: pd.Series) -> float:
    actual = np.array([row["home_goals"] > row["away_goals"], row["home_goals"] == row["away_goals"], row["home_goals"] < row["away_goals"]], dtype=float)
    pred = np.array([row["home_win_prob"], row["draw_prob"], row["away_win_prob"]], dtype=float)
    return float(np.mean((pred - actual) ** 2))


def run_backtest(
    start_date: str,
    end_date: str,
    competitions: list[str] | None = None,
    style_log: pd.DataFrame | str | Path | None = None,
    output_dir: str | Path = REPORTS_DIR,
) -> dict[str, pd.DataFrame | str]:
    log = _load_log(style_log)
    log["date"] = pd.to_datetime(log["date"], errors="coerce")
    if competitions:
        log = log[log["competition"].isin(competitions)]
    match_rows = (
        log.groupby("match_id", as_index=False)
        .agg(date=("date", "first"), competition=("competition", "first"))
        .sort_values("date")
    )
    window = match_rows[(match_rows["date"] >= pd.to_datetime(start_date)) & (match_rows["date"] <= pd.to_datetime(end_date))]
    results = []
    for _, match in window.iterrows():
        teams = log[log["match_id"].eq(match["match_id"])]
        if len(teams) < 2:
            continue
        home_row = teams[teams["is_home"].eq(True)]
        away_row = teams[teams["is_home"].eq(False)]
        if home_row.empty or away_row.empty:
            home_row = teams.iloc[[0]]
            away_row = teams.iloc[[1]]
        home_team = str(home_row.iloc[0]["team"])
        away_team = str(away_row.iloc[0]["team"])
        as_of = match["date"].date().isoformat()
        baseline = baseline_expected_goals(home_team, away_team, as_of, style_log=log)
        baseline_probs = _projection_from_xg(float(baseline["home_xg_base"]), float(baseline["away_xg_base"]))
        projection = project_match(home_team, away_team, as_of, style_log=log).iloc[0].to_dict()
        actual_home = int(home_row.iloc[0]["goals_for"])
        actual_away = int(away_row.iloc[0]["goals_for"])
        results.append({
            "match_id": match["match_id"],
            "date": as_of,
            "home_team": home_team,
            "away_team": away_team,
            "home_goals": actual_home,
            "away_goals": actual_away,
            "baseline_home_xg": baseline["home_xg_base"],
            "baseline_away_xg": baseline["away_xg_base"],
            "style_home_xg": projection["home_xg_final"],
            "style_away_xg": projection["away_xg_final"],
            "home_win_prob": projection["home_win_prob"],
            "draw_prob": projection["draw_prob"],
            "away_win_prob": projection["away_win_prob"],
            "over_2_5_prob": projection["over_2_5_prob"],
            "baseline_home_win_prob": baseline_probs["home_win_prob"],
            "baseline_draw_prob": baseline_probs["draw_prob"],
            "baseline_away_win_prob": baseline_probs["away_win_prob"],
        })
    result_df = pd.DataFrame(results)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "backtest_results.csv"
    summary_path = output / "backtest_summary.md"
    if result_df.empty:
        result_df.to_csv(result_path, index=False)
        summary = "# Backtest Summary\n\nNo eligible matches in window.\n"
        summary_path.write_text(summary, encoding="utf-8")
        return {"results": result_df, "summary": summary}

    result_df["home_goals_abs_error"] = (result_df["style_home_xg"] - result_df["home_goals"]).abs()
    result_df["away_goals_abs_error"] = (result_df["style_away_xg"] - result_df["away_goals"]).abs()
    result_df["total_goals_abs_error"] = ((result_df["style_home_xg"] + result_df["style_away_xg"]) - (result_df["home_goals"] + result_df["away_goals"])).abs()
    result_df["wdl_log_loss"] = result_df.apply(_log_loss, axis=1)
    result_df["brier_score"] = result_df.apply(_brier, axis=1)
    result_df["exact_score_hit"] = ((result_df["style_home_xg"].round().astype(int) == result_df["home_goals"]) & (result_df["style_away_xg"].round().astype(int) == result_df["away_goals"]))
    result_df["over_under_2_5_correct"] = ((result_df["over_2_5_prob"] >= 0.5) == ((result_df["home_goals"] + result_df["away_goals"]) > 2.5))
    baseline_total_mae = ((result_df["baseline_home_xg"] + result_df["baseline_away_xg"]) - (result_df["home_goals"] + result_df["away_goals"])).abs().mean()
    style_total_mae = result_df["total_goals_abs_error"].mean()
    calibration_source = result_df.assign(
        prob_bin=pd.cut(result_df["home_win_prob"], bins=[0, .25, .5, .75, 1.0], include_lowest=True),
        actual_home_win=(result_df["home_goals"] > result_df["away_goals"]).astype(float),
    )
    calibration = (
        calibration_source.groupby("prob_bin", observed=False)
        .agg(avg_home_prob=("home_win_prob", "mean"), home_win_rate=("actual_home_win", "mean"), matches=("match_id", "count"))
        .reset_index()
    )

    summary = "\n".join([
        "# Backtest Summary",
        "",
        f"Matches: {len(result_df)}",
        f"Home goals MAE: {result_df['home_goals_abs_error'].mean():.3f}",
        f"Away goals MAE: {result_df['away_goals_abs_error'].mean():.3f}",
        f"Total goals MAE: {style_total_mae:.3f}",
        f"W/D/L log loss: {result_df['wdl_log_loss'].mean():.3f}",
        f"Brier score: {result_df['brier_score'].mean():.3f}",
        f"Exact score hit rate: {result_df['exact_score_hit'].mean():.3f}",
        f"Over/under 2.5 accuracy: {result_df['over_under_2_5_correct'].mean():.3f}",
        f"Style model lift vs baseline total MAE: {baseline_total_mae - style_total_mae:.3f}",
        "",
        "Calibration table is available in the CSV inputs/derived probability bins.",
    ])
    result_df.to_csv(result_path, index=False)
    summary_path.write_text(summary, encoding="utf-8")
    return {"results": result_df, "summary": summary, "calibration": calibration}
