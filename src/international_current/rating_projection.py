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
    best_score = "1-1"
    best_prob = -1.0
    for home_goals in range(6):
        for away_goals in range(6):
            probability = _poisson_probability(home_xg, home_goals) * _poisson_probability(away_xg, away_goals)
            if probability > best_prob:
                best_prob = probability
                best_score = f"{home_goals}-{away_goals}"
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
    warnings = [RATING_ONLY_WARNING, "Elo-style ratings are strength priors only, not style advantages."]
    if fixture is None:
        warnings.append("No current fixture available.")
    if home_rating is None or home_rating.rating_value is None:
        warnings.append(f"Missing rating for {home_team or 'home team'}.")
    if away_rating is None or away_rating.rating_value is None:
        warnings.append(f"Missing rating for {away_team or 'away team'}.")
    if support in {"low_fixture_only", "low_manual_fixture_rating", "insufficient"}:
        warnings.append("Confidence is capped because fixture/rating support is incomplete or manual-only.")
    home_value = float(home_rating.rating_value) if home_rating and home_rating.rating_value is not None else 1800.0
    away_value = float(away_rating.rating_value) if away_rating and away_rating.rating_value is not None else 1800.0
    diff = max(-350.0, min(350.0, home_value - away_value))
    total = max(1.6, min(3.2, base_total + abs(diff) / 900.0 * 0.18))
    home_share = 0.5 + max(-0.18, min(0.18, diff / 900.0))
    home_xg = round(max(0.35, total * home_share), 3)
    away_xg = round(max(0.35, total * (1 - home_share)), 3)
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
        "home_win_probability": home_win,
        "draw_probability": draw,
        "away_win_probability": away_win,
        "most_likely_score": _scoreline(home_xg, away_xg),
        "data_support_level": support,
        "reliability_status": "rating_only_baseline",
        "confidence_score": confidence_score,
        "confidence_label": "Medium-Low" if confidence_score >= 45 else "Low",
        "warnings": " | ".join(dict.fromkeys(warnings)),
    }

