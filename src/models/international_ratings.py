from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.models.international_context import match_weight


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def _team_rows(matches: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, match in matches.iterrows():
        for side, opponent_side in [("home", "away"), ("away", "home")]:
            team = match[f"{side}_team"]
            opponent = match[f"{opponent_side}_team"]
            goals_for = match[f"{side}_score"]
            goals_against = match[f"{opponent_side}_score"]
            if pd.isna(team) or pd.isna(opponent) or pd.isna(goals_for) or pd.isna(goals_against):
                continue
            rows.append({
                "match_id": match["match_id"],
                "date": match["date"],
                "team": team,
                "opponent": opponent,
                "goals_for": float(goals_for),
                "goals_against": float(goals_against),
                "xg_for": match.get(f"{side}_xg_event", pd.NA),
                "xg_against": match.get(f"{opponent_side}_xg_event", pd.NA),
                "match_stage": match.get("match_stage", "unknown"),
                "competition_name": match.get("competition_name", ""),
                "data_mode": match.get("data_mode", "historical_match_results"),
            })
    return pd.DataFrame(rows)


def _weighted_mean(values: pd.Series, weights: np.ndarray) -> float:
    nums = pd.to_numeric(values, errors="coerce")
    mask = nums.notna()
    if not mask.any():
        return float("nan")
    return float(np.average(nums[mask], weights=weights[mask.to_numpy()]))


def build_international_team_ratings(
    matches: pd.DataFrame | str | Path,
    as_of_date: str,
    recent_matches: int = 12,
    decay: float = 0.88,
) -> pd.DataFrame:
    data = _load(matches)
    prior = data[data["date"] < pd.to_datetime(as_of_date)].sort_values("date")
    rows = _team_rows(prior)
    if rows.empty:
        return pd.DataFrame(columns=[
            "team",
            "matches_played",
            "recent_matches_used",
            "goals_for_per_match",
            "goals_against_per_match",
            "xg_for_per_match",
            "xg_against_per_match",
            "attack_rating",
            "defense_rating",
            "raw_team_rating",
            "opponent_adjusted_rating",
            "adjustment_method",
            "tournament_weighted_rating",
            "recency_weighted_rating",
            "data_quality_flags",
            "limitations",
        ])
    base_strength = rows.groupby("team").agg(base_goal_diff=("goals_for", "mean")).to_dict()["base_goal_diff"]
    ratings = []
    for team, history in rows.groupby("team"):
        ordered = history.sort_values("date").tail(recent_matches)
        recency = np.power(decay, np.arange(len(ordered) - 1, -1, -1))
        tournament = np.array([match_weight(stage) for stage in ordered["match_stage"]], dtype=float)
        weights = recency * tournament
        gf = _weighted_mean(ordered["goals_for"], weights)
        ga = _weighted_mean(ordered["goals_against"], weights)
        xgf = _weighted_mean(ordered["xg_for"], weights)
        xga = _weighted_mean(ordered["xg_against"], weights)
        attack = 0.7 * gf + 0.3 * xgf if pd.notna(xgf) else gf
        defense = 0.7 * ga + 0.3 * xga if pd.notna(xga) else ga
        raw = attack - defense
        opponent_avg = float(np.mean([base_strength.get(opponent, 0.0) for opponent in ordered["opponent"]])) if not ordered.empty else 0.0
        adjusted = raw + 0.15 * opponent_avg
        flags = []
        if len(history) < 5:
            flags.append("low_confidence_fewer_than_5_prior_matches")
        if len(history) < 10:
            flags.append("sparse_sample_fewer_than_10_prior_matches")
        if ordered["match_stage"].astype(str).str.lower().eq("unknown").any():
            flags.append("match_type_uncertain")
        if ordered["data_mode"].astype(str).str.contains("historical", na=False).any():
            flags.append("historical_data_only")
        if pd.isna(xgf):
            flags.append("missing_event_xg")
        ratings.append({
            "team": team,
            "matches_played": int(len(history)),
            "recent_matches_used": int(len(ordered)),
            "goals_for_per_match": round(gf, 4),
            "goals_against_per_match": round(ga, 4),
            "xg_for_per_match": round(float(xgf), 4) if pd.notna(xgf) else pd.NA,
            "xg_against_per_match": round(float(xga), 4) if pd.notna(xga) else pd.NA,
            "attack_rating": round(max(0.2, attack), 4),
            "defense_rating": round(max(0.2, defense), 4),
            "raw_team_rating": round(raw, 4),
            "opponent_adjusted_rating": round(adjusted, 4),
            "adjustment_method": "recency_decay_plus_conservative_opponent_goal_strength",
            "tournament_weighted_rating": round(float(np.average(ordered["goals_for"] - ordered["goals_against"], weights=weights)), 4),
            "recency_weighted_rating": round(float(np.average(ordered["goals_for"] - ordered["goals_against"], weights=recency)), 4),
            "data_quality_flags": "|".join(flags) if flags else "usable_historical_international_sample",
            "limitations": "Opponent adjustment is conservative and historical-only; roster quality is not modeled.",
        })
    return pd.DataFrame(ratings)


def get_team_rating(ratings: pd.DataFrame, team: str) -> pd.Series:
    lookup = ratings.set_index("team") if not ratings.empty and "team" in ratings.columns else pd.DataFrame()
    return lookup.loc[team] if team in lookup.index else pd.Series({
        "team": team,
        "matches_played": 0,
        "recent_matches_used": 0,
        "goals_for_per_match": 1.1,
        "goals_against_per_match": 1.1,
        "attack_rating": 1.1,
        "defense_rating": 1.1,
        "opponent_adjusted_rating": 0.0,
        "data_quality_flags": "no_prior_international_matches",
    })

