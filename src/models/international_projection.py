from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.models.international_context import international_home_advantage, normalize_neutral_site
from src.models.international_ratings import build_international_team_ratings, get_team_rating
from src.models.score_projection import _projection_from_xg


INTERNATIONAL_PROFILES = [
    "international_score_projection",
    "international_winner_probability",
    "international_total_goals",
    "international_event_style_context",
    "international_model_only",
]


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def score_international_confidence(team_a: pd.Series, team_b: pd.Series, neutral_site: str, data: pd.DataFrame) -> dict[str, Any]:
    score = 58
    reasons = []
    risks = []
    min_matches = min(int(team_a.get("matches_played", 0)), int(team_b.get("matches_played", 0)))
    if min_matches < 5:
        score -= 32
        risks.append("low_confidence_fewer_than_5_prior_matches")
        reasons.append("At least one national team has fewer than 5 prior matches.")
    elif min_matches < 10:
        score -= 14
        risks.append("sparse_sample_fewer_than_10_prior_matches")
        reasons.append("At least one national team has fewer than 10 prior matches.")
    else:
        score += 8
        reasons.append("Both national teams have a usable historical sample.")
    if normalize_neutral_site(neutral_site) == "unknown":
        score -= 8
        risks.append("neutral_site_unknown")
        reasons.append("Neutral-site status is unknown.")
    if not bool(data.get("has_event_data", pd.Series(dtype=bool)).any()):
        score -= 8
        risks.append("missing_event_data")
        reasons.append("Event/xG data is unavailable for the selected historical sample.")
    else:
        score += 4
        reasons.append("Some historical StatsBomb event data is available.")
    if data.get("data_mode", pd.Series(dtype=str)).astype(str).str.contains("historical", na=False).any():
        score -= 6
        risks.append("historical_data_only")
        reasons.append("The projection uses historical data, not current live international data.")
    risks.append("roster_uncertainty_not_modeled")
    reasons.append("Roster and manager volatility are not modeled.")
    score = int(max(0, min(100, round(score))))
    label = "High" if score >= 75 else "Medium" if score >= 50 else "Low"
    return {
        "confidence_score": score,
        "confidence_label": label,
        "confidence_reasons": " | ".join(dict.fromkeys(reasons)),
        "risk_flags": " | ".join(dict.fromkeys(risks)),
    }


def _baseline_xg(team_a: pd.Series, team_b: pd.Series, neutral_site: str) -> tuple[float, float, list[str]]:
    home_adv, warnings = international_home_advantage(neutral_site)
    league_avg = 1.20
    a_attack = float(team_a.get("attack_rating", league_avg))
    b_attack = float(team_b.get("attack_rating", league_avg))
    a_def = float(team_a.get("defense_rating", league_avg))
    b_def = float(team_b.get("defense_rating", league_avg))
    a_adj = float(team_a.get("opponent_adjusted_rating", 0.0)) * 0.08
    b_adj = float(team_b.get("opponent_adjusted_rating", 0.0)) * 0.08
    team_a_xg = max(0.15, 0.58 * a_attack + 0.42 * b_def + home_adv + a_adj)
    team_b_xg = max(0.15, 0.58 * b_attack + 0.42 * a_def - home_adv / 2 + b_adj)
    return round(team_a_xg, 4), round(team_b_xg, 4), warnings


def project_international_match(
    matches: pd.DataFrame | str | Path,
    team_a: str,
    team_b: str,
    as_of_date: str,
    neutral_site: str = "unknown",
    projection_profile: str = "international_score_projection",
    competition_context: str = "",
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    data = _load(matches)
    profile = projection_profile if projection_profile in INTERNATIONAL_PROFILES else "international_score_projection"
    ratings = build_international_team_ratings(data, as_of_date)
    a = get_team_rating(ratings, team_a)
    b = get_team_rating(ratings, team_b)
    a_base, b_base, context_warnings = _baseline_xg(a, b, neutral_site)
    baseline_mode = "opponent_adjusted_international_baseline"
    if profile == "international_model_only":
        baseline_mode = "goals_only_international_baseline"
    elif profile == "international_event_style_context" and bool(data.get("has_event_data", pd.Series(dtype=bool)).any()):
        baseline_mode = "event_xg_informed_international_baseline"
    if profile == "international_total_goals":
        total = (a_base + b_base) * 0.95
        share = a_base / max(0.01, a_base + b_base)
        a_base, b_base = round(total * share, 4), round(total * (1 - share), 4)
    probs = _projection_from_xg(a_base, b_base)
    confidence = score_international_confidence(a, b, neutral_site, data[data["date"] < pd.to_datetime(as_of_date)])
    row = {
        "as_of_date": as_of_date,
        "team_a": team_a,
        "team_b": team_b,
        "neutral_site": normalize_neutral_site(neutral_site),
        "competition_context": competition_context,
        "projection_profile": profile,
        "baseline_mode_used": baseline_mode,
        "team_a_xg_base": a_base,
        "team_b_xg_base": b_base,
        "team_a_xg_final": a_base,
        "team_b_xg_final": b_base,
        "projected_total": probs["projected_total"],
        "most_likely_score": probs["most_likely_score"],
        "team_a_win_prob": probs["home_win_prob"],
        "draw_prob": probs["draw_prob"],
        "team_b_win_prob": probs["away_win_prob"],
        "over_1_5_prob": probs["over_1_5_prob"],
        "over_2_5_prob": probs["over_2_5_prob"],
        "under_2_5_prob": probs["under_2_5_prob"],
        "btts_prob": probs["btts_prob"],
        "confidence_score": confidence["confidence_score"],
        "confidence_label": confidence["confidence_label"],
        "confidence_reasons": confidence["confidence_reasons"],
        "risk_flags": confidence["risk_flags"],
        "data_quality_flags": " | ".join([str(a.get("data_quality_flags", "")), str(b.get("data_quality_flags", ""))]),
        "international_context_warnings": " | ".join(context_warnings + ["current_live_international_data_missing", "historical_statsbomb_data_not_live_current_data"]),
        "data_mode": "true_event_style_historical" if bool(data.get("has_event_data", pd.Series(dtype=bool)).any()) else "sparse_free_data_projection",
    }
    result = pd.DataFrame([row])
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
    return result

