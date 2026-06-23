from __future__ import annotations

from typing import Any

import pandas as pd


def _has_numeric(data: pd.DataFrame, columns: list[str]) -> bool:
    return all(col in data.columns and pd.to_numeric(data[col], errors="coerce").notna().any() for col in columns)


def _label(score: int) -> str:
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"


def _baseline_disagreement(baselines: dict[str, dict[str, Any]]) -> float:
    totals = [
        float(b["home_xg_base"]) + float(b["away_xg_base"])
        for b in baselines.values()
        if b.get("available", True) and pd.notna(b.get("home_xg_base")) and pd.notna(b.get("away_xg_base"))
    ]
    if len(totals) < 2:
        return 0.0
    return max(totals) - min(totals)


def score_projection_confidence(
    data: pd.DataFrame,
    baseline: dict[str, Any],
    baselines: dict[str, dict[str, Any]],
    market_gap: dict[str, Any],
    proxy_adjustments_enabled: bool,
    projection_profile: str,
) -> dict[str, Any]:
    score = 72
    reasons: list[str] = []
    risk_flags: list[str] = []
    disagreement_flags: list[str] = []
    home_prior = int(baseline.get("home_prior_matches", 0) or 0)
    away_prior = int(baseline.get("away_prior_matches", 0) or 0)
    if home_prior < 6 or away_prior < 6:
        score -= 35
        reasons.append("Fewer than 6 prior matches for at least one team.")
        risk_flags.append("low_prior_match_sample")
    elif home_prior >= 10 and away_prior >= 10:
        score += 8
        reasons.append("Both teams have a usable prior-match sample.")
    else:
        reasons.append("Prior-match sample is adequate but still modest.")

    if not _has_numeric(data, ["home_goals", "away_goals"]):
        score -= 45
        reasons.append("Goals data is missing or unusable.")
        risk_flags.append("missing_goals_data")
    else:
        reasons.append("Goals data is available.")

    if not _has_numeric(data, ["home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target"]):
        score -= 8
        reasons.append("Shots/SOT data is missing or sparse.")
        risk_flags.append("limited_shot_data")
    else:
        score += 4
        reasons.append("Shots/SOT data is available.")

    if not _has_numeric(data, ["home_corners", "away_corners"]):
        score -= 3
        risk_flags.append("limited_corner_data")

    odds_available = all(market_gap.get(k) is not None for k in ["market_home_prob", "market_draw_prob", "market_away_prob"])
    totals_available = market_gap.get("market_over_2_5_prob") is not None
    if odds_available:
        score += 4 if projection_profile in {"winner_probability", "market_anchored"} else 2
        reasons.append("1X2 odds are available for market comparison.")
    else:
        score -= 7 if projection_profile in {"winner_probability", "market_anchored"} else 4
        reasons.append("1X2 odds are missing for market comparison.")
        risk_flags.append("missing_1x2_odds")
    if totals_available:
        reasons.append("Totals odds are available for over/under context.")
    else:
        score -= 4 if projection_profile == "total_goals" else 1
        risk_flags.append("missing_totals_odds")

    disagreement = _baseline_disagreement(baselines)
    if disagreement >= 0.45:
        score -= 12
        disagreement_flags.append("baseline_total_disagreement_high")
        reasons.append(f"Baseline projected totals differ by {disagreement:.2f} goals.")
    elif disagreement >= 0.25:
        score -= 6
        disagreement_flags.append("baseline_total_disagreement_medium")
    else:
        score += 3
        reasons.append("Baseline modes broadly agree on match total.")

    largest_gap = market_gap.get("largest_gap_value")
    if largest_gap is not None and abs(float(largest_gap)) >= 0.12:
        score -= 8
        disagreement_flags.append("model_market_probability_gap_high")
        reasons.append("Model and market probabilities have a large gap; this is not a betting signal.")
    elif largest_gap is not None and abs(float(largest_gap)) >= 0.07:
        score -= 4
        disagreement_flags.append("model_market_probability_gap_medium")

    if proxy_adjustments_enabled:
        score -= 4
        risk_flags.append("proxy_adjustments_enabled")
        reasons.append("Proxy score adjustments are enabled, adding model risk.")
    else:
        reasons.append("Proxy score adjustments are disabled by default.")

    if baseline.get("baseline_mode") in {"market", "totals_market"} and not baseline.get("available", True):
        score -= 8
        risk_flags.append("baseline_fallback_used")

    score = int(max(0, min(100, round(score))))
    if not reasons:
        reasons.append("No confidence details available.")
    return {
        "confidence_score": score,
        "confidence_label": _label(score),
        "confidence_reasons": " | ".join(dict.fromkeys(reasons)),
        "risk_flags": " | ".join(dict.fromkeys(risk_flags)) if risk_flags else "none",
        "disagreement_flags": " | ".join(dict.fromkeys(disagreement_flags)) if disagreement_flags else "none",
    }

