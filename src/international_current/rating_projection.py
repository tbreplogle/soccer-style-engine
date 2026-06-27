from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.international_current.current_international_schema import CurrentInternationalFixture, CurrentInternationalTeamRating


RATING_ONLY_WARNING = (
    "This is a baseline score projection based on fixture + rating support only. "
    "It does not include current event data, xG, lineups, injuries, or style-aware matchup inputs yet."
)


@dataclass(frozen=True)
class RatingProjectionInput:
    fixture: CurrentInternationalFixture | None
    home_rating: CurrentInternationalTeamRating | None
    away_rating: CurrentInternationalTeamRating | None


def build_rating_lookup(ratings: list[CurrentInternationalTeamRating]) -> dict[str, CurrentInternationalTeamRating]:
    return {rating.team: rating for rating in ratings if rating.team}


def _poisson_probability(lam: float, goals: int) -> float:
    return math.exp(-lam) * (lam ** goals) / math.factorial(goals)


def _scoreline(home_xg: float, away_xg: float) -> str:
    best_score = "1 - 1"
    best_prob = -1.0
    for home_goals in range(6):
        for away_goals in range(6):
            probability = _poisson_probability(home_xg, home_goals) * _poisson_probability(away_xg, away_goals)
            if probability > best_prob:
                best_prob = probability
                best_score = f"{home_goals} - {away_goals}"
    return best_score


def _wdl_probabilities(home_xg: float, away_xg: float) -> tuple[float, float, float]:
    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    for home_goals in range(8):
        for away_goals in range(8):
            probability = _poisson_probability(home_xg, home_goals) * _poisson_probability(away_xg, away_goals)
            if home_goals > away_goals:
                home_win += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                away_win += probability
    total = max(0.0001, home_win + draw + away_win)
    return round(home_win / total, 4), round(draw / total, 4), round(away_win / total, 4)


def _safety_guard_xg(value: float, *, team_label: str) -> tuple[float, bool, str]:
    if pd.isna(value):
        return 1.0, True, f"{team_label} xG was missing/non-numeric; neutral fallback applied."
    if value < 0.05:
        return 0.05, True, f"{team_label} xG raised to broad non-negative safety guard 0.05."
    if value > 5.0:
        return 5.0, True, f"{team_label} xG lowered to broad sanity guard 5.00."
    return value, False, ""


def data_support_for_rating_projection(
    fixture: CurrentInternationalFixture | None,
    home_rating: CurrentInternationalTeamRating | None,
    away_rating: CurrentInternationalTeamRating | None,
) -> str:
    has_rating = bool(home_rating and away_rating and home_rating.rating_value is not None and away_rating.rating_value is not None)
    if not fixture:
        return "insufficient"
    is_manual = fixture.source_name == "manual_current_fixture" or fixture.reliability_status == "manual_fallback"
    if is_manual:
        return "low_manual_fixture_rating"
    if has_rating:
        return "medium_current_fixture_rating"
    return "low_fixture_only"


def rating_status_and_warning(
    home_team: str,
    away_team: str,
    home_rating: CurrentInternationalTeamRating | None,
    away_rating: CurrentInternationalTeamRating | None,
) -> tuple[str, str]:
    home_missing = home_rating is None or home_rating.rating_value is None
    away_missing = away_rating is None or away_rating.rating_value is None
    if home_missing and away_missing:
        return "both_ratings_missing", "Both team ratings missing; neutral baseline xG split used."
    if home_missing:
        return "home_rating_missing", "One team rating missing; fallback rating used for missing side."
    if away_missing:
        return "away_rating_missing", "One team rating missing; fallback rating used for missing side."
    return "both_ratings_available", ""


def project_from_fixture_and_ratings(
    fixture: CurrentInternationalFixture | None,
    home_rating: CurrentInternationalTeamRating | None,
    away_rating: CurrentInternationalTeamRating | None,
    *,
    base_total: float = 2.35,
) -> dict[str, Any]:
    home_team = fixture.home_team if fixture else (home_rating.team if home_rating else "")
    away_team = fixture.away_team if fixture else (away_rating.team if away_rating else "")
    support = data_support_for_rating_projection(fixture, home_rating, away_rating)
    rating_status, rating_warning = rating_status_and_warning(home_team, away_team, home_rating, away_rating)
    warnings = [RATING_ONLY_WARNING, "Elo-style ratings are strength priors only, not style advantages."]
    if fixture is None:
        warnings.append("No current fixture available.")
    if home_rating is None or home_rating.rating_value is None:
        warnings.append(f"Missing rating for {home_team or 'home team'}.")
    if away_rating is None or away_rating.rating_value is None:
        warnings.append(f"Missing rating for {away_team or 'away team'}.")
    if rating_warning:
        warnings.append(rating_warning)
    if support in {"low_fixture_only", "low_manual_fixture_rating", "insufficient"}:
        warnings.append("Confidence is capped because fixture/rating support is incomplete or manual-only.")
    home_value = float(home_rating.rating_value) if home_rating and home_rating.rating_value is not None else 1800.0
    away_value = float(away_rating.rating_value) if away_rating and away_rating.rating_value is not None else 1800.0
    diff = home_value - away_value
    total = base_total + math.log1p(abs(diff)) / math.log1p(900.0) * 0.32
    home_share = 0.5 + 0.28 * math.tanh(diff / 900.0)
    raw_home_xg = total * home_share
    raw_away_xg = total * (1 - home_share)
    home_guarded, home_guard, home_guard_reason = _safety_guard_xg(raw_home_xg, team_label="home")
    away_guarded, away_guard, away_guard_reason = _safety_guard_xg(raw_away_xg, team_label="away")
    home_xg = round(home_guarded, 3)
    away_xg = round(away_guarded, 3)
    xg_safety_guard_applied = bool(home_guard or away_guard)
    xg_safety_guard_reason = " | ".join(reason for reason in [home_guard_reason, away_guard_reason] if reason)
    home_win, draw, away_win = _wdl_probabilities(home_xg, away_xg)
    confidence_score = 48 if support == "medium_current_fixture_rating" else 34 if support == "low_manual_fixture_rating" else 28 if support == "low_fixture_only" else 15
    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_rating": home_value if home_rating and home_rating.rating_value is not None else pd.NA,
        "away_rating": away_value if away_rating and away_rating.rating_value is not None else pd.NA,
        "rating_diff": round(diff, 1) if home_rating and away_rating and home_rating.rating_value is not None and away_rating.rating_value is not None else pd.NA,
        "projected_home_xg": home_xg,
        "projected_away_xg": away_xg,
        "projected_total": round(home_xg + away_xg, 3),
        "xg_safety_guard_applied": xg_safety_guard_applied,
        "xg_safety_guard_reason": xg_safety_guard_reason,
        "home_win_probability": home_win,
        "draw_probability": draw,
        "away_win_probability": away_win,
        "most_likely_score": _scoreline(home_xg, away_xg),
        "data_support_level": support,
        "rating_status": rating_status,
        "rating_warning": rating_warning,
        "reliability_status": "rating_only_baseline",
        "confidence_score": confidence_score,
        "confidence_label": "Medium-Low" if confidence_score >= 45 else "Low",
        "warnings": " | ".join(dict.fromkeys(warnings)),
    }

