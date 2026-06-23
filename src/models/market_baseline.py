from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.features.free_style_proxies import build_current_team_ratings


BASELINE_MODES = ["goals", "shots", "market", "totals_market", "blended"]


def convert_decimal_odds_to_implied_probs(*odds: float | int | None) -> list[float | None]:
    probs: list[float | None] = []
    for odd in odds:
        value = pd.to_numeric(odd, errors="coerce")
        probs.append(float(1 / value) if pd.notna(value) and value > 1 else None)
    return probs


def remove_vig_basic(probs: list[float | None]) -> list[float | None]:
    clean = [p for p in probs if p is not None and pd.notna(p)]
    total = sum(clean)
    if not clean or total <= 0 or len(clean) != len(probs):
        return [None for _ in probs]
    return [float(p / total) for p in probs]  # type: ignore[operator]


def estimate_market_home_away_strength(home_odds: float | None, draw_odds: float | None, away_odds: float | None) -> dict[str, float | None]:
    probs = remove_vig_basic(convert_decimal_odds_to_implied_probs(home_odds, draw_odds, away_odds))
    if any(p is None for p in probs):
        return {"home_win_prob": None, "draw_prob": None, "away_win_prob": None, "home_strength_share": None}
    home, draw, away = probs  # type: ignore[misc]
    decisive = max(0.01, float(home) + float(away))
    return {
        "home_win_prob": float(home),
        "draw_prob": float(draw),
        "away_win_prob": float(away),
        "home_strength_share": float(home / decisive),
    }


def estimate_market_total_pressure_from_ou25(over_odds: float | None, under_odds: float | None) -> dict[str, float | None]:
    probs = remove_vig_basic(convert_decimal_odds_to_implied_probs(over_odds, under_odds))
    if any(p is None for p in probs):
        return {"over_2_5_prob": None, "under_2_5_prob": None, "total_pressure": None}
    over, under = probs  # type: ignore[misc]
    return {"over_2_5_prob": float(over), "under_2_5_prob": float(under), "total_pressure": float(over - under)}


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    optional_cols = [
        "home_shots",
        "away_shots",
        "home_shots_on_target",
        "away_shots_on_target",
        "home_corners",
        "away_corners",
        "home_fouls",
        "away_fouls",
        "home_yellow_cards",
        "away_yellow_cards",
        "home_red_cards",
        "away_red_cards",
        "home_odds_close",
        "draw_odds_close",
        "away_odds_close",
        "over_2_5_odds_close",
        "under_2_5_odds_close",
    ]
    for col in optional_cols:
        if col not in out.columns:
            out[col] = pd.NA
    return out


def _team_value(row: pd.Series, key: str, default: float) -> float:
    value = row.get(key, default)
    return float(value) if pd.notna(value) else default


def _league_avgs(prior: pd.DataFrame) -> dict[str, float]:
    goals = pd.concat([prior["home_goals"], prior["away_goals"]])
    shots = pd.concat([prior.get("home_shots", pd.Series(dtype=float)), prior.get("away_shots", pd.Series(dtype=float))])
    sot = pd.concat([prior.get("home_shots_on_target", pd.Series(dtype=float)), prior.get("away_shots_on_target", pd.Series(dtype=float))])
    return {
        "goals_per_team": max(0.2, float(pd.to_numeric(goals, errors="coerce").mean())),
        "total_goals": max(0.4, float(pd.to_numeric(prior["total_goals"], errors="coerce").mean())),
        "goals_per_shot": float(pd.to_numeric(goals, errors="coerce").sum() / max(1, pd.to_numeric(shots, errors="coerce").sum())),
        "goals_per_sot": float(pd.to_numeric(goals, errors="coerce").sum() / max(1, pd.to_numeric(sot, errors="coerce").sum())),
    }


def goals_baseline_xg(matches: pd.DataFrame | str | Path, home_team: str, away_team: str, as_of_date: str, neutral_site: bool = False) -> dict[str, Any]:
    data = _load(matches)
    prior = data[data["date"] < pd.to_datetime(as_of_date)].copy()
    if prior.empty:
        return {"home_xg_base": 1.35, "away_xg_base": 1.10, "baseline_mode": "goals", "available": True, "home_prior_matches": 0, "away_prior_matches": 0}
    ratings = build_current_team_ratings(prior, as_of_date).set_index("team")
    avgs = _league_avgs(prior)
    home = ratings.loc[home_team] if home_team in ratings.index else pd.Series(dtype=float)
    away = ratings.loc[away_team] if away_team in ratings.index else pd.Series(dtype=float)
    home_attack = _team_value(home, "goals_for_per_match", avgs["goals_per_team"])
    away_attack = _team_value(away, "goals_for_per_match", avgs["goals_per_team"])
    home_def = _team_value(home, "goals_against_per_match", avgs["goals_per_team"])
    away_def = _team_value(away, "goals_against_per_match", avgs["goals_per_team"])
    home_adv = 0.12 if not neutral_site else 0.0
    return {
        "home_xg_base": round(max(0.15, 0.58 * home_attack + 0.42 * away_def + home_adv), 4),
        "away_xg_base": round(max(0.15, 0.58 * away_attack + 0.42 * home_def - home_adv / 2), 4),
        "baseline_mode": "goals",
        "available": True,
        "home_prior_matches": int(_team_value(home, "recent_matches_used", 0)),
        "away_prior_matches": int(_team_value(away, "recent_matches_used", 0)),
    }


def shots_baseline_xg(matches: pd.DataFrame | str | Path, home_team: str, away_team: str, as_of_date: str) -> dict[str, Any]:
    data = _load(matches)
    prior = data[data["date"] < pd.to_datetime(as_of_date)].copy()
    needed = {"home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target"}
    if prior.empty or not needed.issubset(prior.columns) or prior[list(needed)].isna().all().any():
        fallback = goals_baseline_xg(data, home_team, away_team, as_of_date)
        fallback.update({"baseline_mode": "shots", "available": False, "fallback": "goals"})
        return fallback
    ratings = build_current_team_ratings(prior, as_of_date).set_index("team")
    avgs = _league_avgs(prior)
    home = ratings.loc[home_team] if home_team in ratings.index else pd.Series(dtype=float)
    away = ratings.loc[away_team] if away_team in ratings.index else pd.Series(dtype=float)
    home_shot_xg = 0.55 * _team_value(home, "shots_for_per_match", 10) * avgs["goals_per_shot"] + 0.45 * _team_value(home, "sot_for_per_match", 4) * avgs["goals_per_sot"]
    away_shot_xg = 0.55 * _team_value(away, "shots_for_per_match", 10) * avgs["goals_per_shot"] + 0.45 * _team_value(away, "sot_for_per_match", 4) * avgs["goals_per_sot"]
    home_allowed = 0.55 * _team_value(away, "shots_against_per_match", 10) * avgs["goals_per_shot"] + 0.45 * _team_value(away, "sot_against_per_match", 4) * avgs["goals_per_sot"]
    away_allowed = 0.55 * _team_value(home, "shots_against_per_match", 10) * avgs["goals_per_shot"] + 0.45 * _team_value(home, "sot_against_per_match", 4) * avgs["goals_per_sot"]
    return {
        "home_xg_base": round(max(0.15, 0.55 * home_shot_xg + 0.45 * home_allowed + 0.08), 4),
        "away_xg_base": round(max(0.15, 0.55 * away_shot_xg + 0.45 * away_allowed - 0.04), 4),
        "baseline_mode": "shots",
        "available": True,
        "home_prior_matches": int(_team_value(home, "recent_matches_used", 0)),
        "away_prior_matches": int(_team_value(away, "recent_matches_used", 0)),
    }


def _latest_matchup_row(data: pd.DataFrame, home_team: str, away_team: str, as_of_date: str) -> pd.Series | None:
    rows = data[(data["date"] < pd.to_datetime(as_of_date)) & data["home_team"].eq(home_team) & data["away_team"].eq(away_team)].sort_values("date")
    if rows.empty:
        rows = data[(data["date"] < pd.to_datetime(as_of_date)) & (data["home_team"].eq(home_team) | data["away_team"].eq(away_team))].sort_values("date")
    return rows.iloc[-1] if not rows.empty else None


def odds_implied_baseline_xg(matches: pd.DataFrame | str | Path, home_team: str, away_team: str, as_of_date: str) -> dict[str, Any]:
    data = _load(matches)
    goal_base = goals_baseline_xg(data, home_team, away_team, as_of_date)
    row = _latest_matchup_row(data, home_team, away_team, as_of_date)
    if row is None:
        goal_base.update({"baseline_mode": "market", "available": False, "fallback": "goals"})
        return goal_base
    market = estimate_market_home_away_strength(row.get("home_odds_close"), row.get("draw_odds_close"), row.get("away_odds_close"))
    if market["home_strength_share"] is None:
        goal_base.update({"baseline_mode": "market", "available": False, "fallback": "goals"})
        return goal_base
    total = goal_base["home_xg_base"] + goal_base["away_xg_base"]
    home_share = 0.65 * (float(goal_base["home_xg_base"]) / total) + 0.35 * float(market["home_strength_share"])
    return {
        **goal_base,
        "home_xg_base": round(max(0.15, total * home_share), 4),
        "away_xg_base": round(max(0.15, total * (1 - home_share)), 4),
        "baseline_mode": "market",
        "available": True,
    }


def totals_market_baseline_xg(matches: pd.DataFrame | str | Path, home_team: str, away_team: str, as_of_date: str) -> dict[str, Any]:
    data = _load(matches)
    goal_base = goals_baseline_xg(data, home_team, away_team, as_of_date)
    row = _latest_matchup_row(data, home_team, away_team, as_of_date)
    if row is None:
        goal_base.update({"baseline_mode": "totals_market", "available": False, "fallback": "goals"})
        return goal_base
    pressure = estimate_market_total_pressure_from_ou25(row.get("over_2_5_odds_close"), row.get("under_2_5_odds_close"))
    if pressure["total_pressure"] is None:
        goal_base.update({"baseline_mode": "totals_market", "available": False, "fallback": "goals"})
        return goal_base
    prior = data[data["date"] < pd.to_datetime(as_of_date)]
    league_total = _league_avgs(prior)["total_goals"] if not prior.empty else 2.55
    market_total = max(1.0, league_total + float(pressure["total_pressure"]) * 1.25)
    base_total = float(goal_base["home_xg_base"]) + float(goal_base["away_xg_base"])
    blended_total = 0.65 * base_total + 0.35 * market_total
    home_share = float(goal_base["home_xg_base"]) / max(0.01, base_total)
    return {
        **goal_base,
        "home_xg_base": round(max(0.15, blended_total * home_share), 4),
        "away_xg_base": round(max(0.15, blended_total * (1 - home_share)), 4),
        "baseline_mode": "totals_market",
        "available": True,
    }


def blend_baseline_xg(components: dict[str, dict[str, Any]], weights: dict[str, float] | None = None) -> dict[str, Any]:
    weights = weights or {"goals": 0.45, "shots": 0.25, "market": 0.20, "totals_market": 0.10}
    available = {mode: comp for mode, comp in components.items() if comp.get("available", True)}
    if not available:
        available = {"goals": components["goals"]}
    active_weights = {mode: weights.get(mode, 0) for mode in available}
    total_weight = sum(active_weights.values()) or 1.0
    home = sum(float(available[mode]["home_xg_base"]) * active_weights[mode] for mode in available) / total_weight
    away = sum(float(available[mode]["away_xg_base"]) * active_weights[mode] for mode in available) / total_weight
    goals = components.get("goals", {})
    return {
        "home_xg_base": round(max(0.15, home), 4),
        "away_xg_base": round(max(0.15, away), 4),
        "baseline_mode": "blended",
        "available": True,
        "component_modes": ",".join(sorted(available)),
        "home_prior_matches": goals.get("home_prior_matches", 0),
        "away_prior_matches": goals.get("away_prior_matches", 0),
    }


def estimate_current_baseline_xg(
    matches: pd.DataFrame | str | Path,
    home_team: str,
    away_team: str,
    as_of_date: str,
    baseline_mode: str = "blended",
    neutral_site: bool = False,
    blend_weights: dict[str, float] | None = None,
    market_enabled: bool = True,
) -> dict[str, Any]:
    data = _load(matches)
    mode = baseline_mode if baseline_mode in BASELINE_MODES else "blended"
    components = {
        "goals": goals_baseline_xg(data, home_team, away_team, as_of_date, neutral_site=neutral_site),
        "shots": shots_baseline_xg(data, home_team, away_team, as_of_date),
    }
    if market_enabled:
        components["market"] = odds_implied_baseline_xg(data, home_team, away_team, as_of_date)
        components["totals_market"] = totals_market_baseline_xg(data, home_team, away_team, as_of_date)
    else:
        components["market"] = {**components["goals"], "baseline_mode": "market", "available": False, "fallback": "market_disabled"}
        components["totals_market"] = {**components["goals"], "baseline_mode": "totals_market", "available": False, "fallback": "market_disabled"}
    if mode == "blended":
        return blend_baseline_xg(components, weights=blend_weights)
    return components[mode]
