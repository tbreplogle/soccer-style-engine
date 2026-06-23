from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.agents.matchup_intelligence_agent import analyze_matchup
from src.config import PROJECTIONS_DIR
from src.features.team_aggregates import build_team_style_profile
from src.models.baseline_strength import baseline_expected_goals
from src.models.xg_adjuster import style_adjustment_for_team


def _poisson_probs(lam: float, max_goals: int = 10) -> np.ndarray:
    probs = np.array([math.exp(-lam) * lam**k / math.factorial(k) for k in range(max_goals + 1)], dtype=float)
    probs[-1] += max(0.0, 1.0 - probs.sum())
    return probs


def score_distribution(home_xg: float, away_xg: float, max_goals: int = 10) -> pd.DataFrame:
    hp = _poisson_probs(home_xg, max_goals=max_goals)
    ap = _poisson_probs(away_xg, max_goals=max_goals)
    rows = []
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            rows.append({"home_goals": h, "away_goals": a, "probability": float(hp[h] * ap[a])})
    return pd.DataFrame(rows)


def _projection_from_xg(home_xg: float, away_xg: float) -> dict[str, Any]:
    dist = score_distribution(home_xg, away_xg)
    home_win = float(dist.loc[dist["home_goals"] > dist["away_goals"], "probability"].sum())
    draw = float(dist.loc[dist["home_goals"] == dist["away_goals"], "probability"].sum())
    away_win = float(dist.loc[dist["home_goals"] < dist["away_goals"], "probability"].sum())
    totals = dist["home_goals"] + dist["away_goals"]
    most = dist.loc[dist["probability"].idxmax()]
    return {
        "most_likely_score": f"{int(most['home_goals'])}-{int(most['away_goals'])}",
        "projected_total": round(home_xg + away_xg, 4),
        "home_win_prob": home_win,
        "draw_prob": draw,
        "away_win_prob": away_win,
        "over_1_5_prob": float(dist.loc[totals > 1.5, "probability"].sum()),
        "over_2_5_prob": float(dist.loc[totals > 2.5, "probability"].sum()),
        "under_2_5_prob": float(dist.loc[totals < 2.5, "probability"].sum()),
        "btts_prob": float(dist.loc[(dist["home_goals"] > 0) & (dist["away_goals"] > 0), "probability"].sum()),
    }


def project_match(
    home_team: str,
    away_team: str,
    as_of_date: str,
    style_log: pd.DataFrame | str | Path | None = None,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    baseline = baseline_expected_goals(home_team, away_team, as_of_date, style_log=style_log)
    home_profile = build_team_style_profile(home_team, as_of_date, style_log=style_log)
    away_profile = build_team_style_profile(away_team, as_of_date, style_log=style_log)
    home_adj, home_reasons = style_adjustment_for_team(home_profile, away_profile)
    away_adj, away_reasons = style_adjustment_for_team(away_profile, home_profile)
    home_final = max(0.05, float(baseline["home_xg_base"]) + home_adj)
    away_final = max(0.05, float(baseline["away_xg_base"]) + away_adj)
    probs = _projection_from_xg(home_final, away_final)
    matchup = analyze_matchup(home_team, away_team, as_of_date, style_log=style_log)
    low_conf = int(baseline["home_prior_matches"]) < 5 or int(baseline["away_prior_matches"]) < 5
    flags = list(matchup["data_quality_flags"])
    if low_conf:
        flags.append("low_confidence_fewer_than_5_prior_matches")

    row = {
        "date": as_of_date,
        "home_team": home_team,
        "away_team": away_team,
        "home_xg_base": baseline["home_xg_base"],
        "away_xg_base": baseline["away_xg_base"],
        "home_xg_style_adjustment": home_adj,
        "away_xg_style_adjustment": away_adj,
        "home_xg_final": round(home_final, 4),
        "away_xg_final": round(away_final, 4),
        **probs,
        "confidence": "Low" if low_conf else "Medium",
        "data_quality_flags": " | ".join(flags),
        "style_explanation": "; ".join(home_reasons + away_reasons) or matchup["style_summary"],
    }
    result = pd.DataFrame([row])
    output = Path(output_path) if output_path else PROJECTIONS_DIR / "match_projection.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    return result
