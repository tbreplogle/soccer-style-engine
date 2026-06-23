from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROXY_NAMES = [
    "control_proxy",
    "attacking_pressure_proxy",
    "defensive_shell_proxy",
    "tempo_proxy",
    "chaos_proxy",
    "finishing_proxy",
    "chance_quality_proxy",
    "directness_proxy",
    "under_profile_proxy",
]


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    return data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)


def _team_rows(matches: pd.DataFrame) -> pd.DataFrame:
    home = pd.DataFrame({
        "match_id": matches["match_id"],
        "date": matches["date"],
        "league": matches["league"],
        "season": matches["season"],
        "team": matches["home_team"],
        "opponent": matches["away_team"],
        "is_home": True,
        "goals_for": matches["home_goals"],
        "goals_against": matches["away_goals"],
        "shots_for": matches["home_shots"],
        "shots_against": matches["away_shots"],
        "sot_for": matches["home_shots_on_target"],
        "sot_against": matches["away_shots_on_target"],
        "corners_for": matches["home_corners"],
        "corners_against": matches["away_corners"],
        "fouls_for": matches["home_fouls"],
        "fouls_against": matches["away_fouls"],
        "yellow_cards": matches["home_yellow_cards"],
        "red_cards": matches["home_red_cards"],
        "team_odds": matches["home_odds_close"],
        "opp_odds": matches["away_odds_close"],
        "result": matches["result"],
    })
    away = pd.DataFrame({
        "match_id": matches["match_id"],
        "date": matches["date"],
        "league": matches["league"],
        "season": matches["season"],
        "team": matches["away_team"],
        "opponent": matches["home_team"],
        "is_home": False,
        "goals_for": matches["away_goals"],
        "goals_against": matches["home_goals"],
        "shots_for": matches["away_shots"],
        "shots_against": matches["home_shots"],
        "sot_for": matches["away_shots_on_target"],
        "sot_against": matches["home_shots_on_target"],
        "corners_for": matches["away_corners"],
        "corners_against": matches["home_corners"],
        "fouls_for": matches["away_fouls"],
        "fouls_against": matches["home_fouls"],
        "yellow_cards": matches["away_yellow_cards"],
        "red_cards": matches["away_red_cards"],
        "team_odds": matches["away_odds_close"],
        "opp_odds": matches["home_odds_close"],
        "result": matches["result"].map({"H": "A", "A": "H", "D": "D"}),
    })
    rows = pd.concat([home, away], ignore_index=True)
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows["points"] = rows["result"].map({"H": 3, "D": 1, "A": 0}).fillna(0)
    rows["total_shots"] = pd.to_numeric(rows["shots_for"], errors="coerce") + pd.to_numeric(rows["shots_against"], errors="coerce")
    rows["total_corners"] = pd.to_numeric(rows["corners_for"], errors="coerce") + pd.to_numeric(rows["corners_against"], errors="coerce")
    rows["total_goals"] = pd.to_numeric(rows["goals_for"], errors="coerce") + pd.to_numeric(rows["goals_against"], errors="coerce")
    rows["total_cards_fouls"] = (
        pd.to_numeric(rows["yellow_cards"], errors="coerce").fillna(0)
        + pd.to_numeric(rows["red_cards"], errors="coerce").fillna(0) * 2
        + pd.to_numeric(rows["fouls_for"], errors="coerce").fillna(0) / 5
    )
    implied = 1 / pd.to_numeric(rows["team_odds"], errors="coerce")
    opp_implied = 1 / pd.to_numeric(rows["opp_odds"], errors="coerce")
    rows["market_implied_strength"] = implied / (implied + opp_implied)
    return rows


def _weighted_mean(series: pd.Series, weights: np.ndarray) -> float:
    vals = pd.to_numeric(series, errors="coerce")
    mask = vals.notna()
    if not mask.any():
        return float("nan")
    return float(np.average(vals[mask], weights=weights[mask.to_numpy()]))


def build_current_team_ratings(
    matches: pd.DataFrame | str | Path,
    as_of_date: str,
    recent_matches: int = 8,
    decay: float = 0.85,
) -> pd.DataFrame:
    data = _load(matches)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    prior_matches = data[data["date"] < pd.to_datetime(as_of_date)].copy()
    rows = _team_rows(prior_matches) if not prior_matches.empty else pd.DataFrame()
    out = []
    for team in sorted(set(data["home_team"]).union(set(data["away_team"]))):
        team_history = rows[rows["team"].eq(team)].sort_values("date").tail(recent_matches) if not rows.empty else pd.DataFrame()
        weights = np.power(decay, np.arange(len(team_history) - 1, -1, -1)) if not team_history.empty else np.array([])
        row: dict[str, Any] = {"team": team, "as_of_date": as_of_date, "matches_played": int(len(rows[rows["team"].eq(team)])) if not rows.empty else 0, "recent_matches_used": int(len(team_history))}
        for metric in ["goals_for", "goals_against", "shots_for", "shots_against", "sot_for", "sot_against", "corners_for", "corners_against", "total_shots", "total_corners", "points", "market_implied_strength", "total_goals", "total_cards_fouls", "yellow_cards", "red_cards"]:
            row[f"{metric}_per_match"] = _weighted_mean(team_history[metric], weights) if not team_history.empty and metric in team_history else float("nan")
        row["home_matches"] = int(team_history["is_home"].sum()) if not team_history.empty else 0
        row["away_matches"] = int((~team_history["is_home"]).sum()) if not team_history.empty else 0
        row["shot_share"] = row["shots_for_per_match"] / max(0.01, row["shots_for_per_match"] + row["shots_against_per_match"]) if pd.notna(row["shots_for_per_match"]) else float("nan")
        row["corner_share"] = row["corners_for_per_match"] / max(0.01, row["corners_for_per_match"] + row["corners_against_per_match"]) if pd.notna(row["corners_for_per_match"]) else float("nan")
        row["goals_per_shot"] = row["goals_for_per_match"] / max(0.01, row["shots_for_per_match"]) if pd.notna(row["shots_for_per_match"]) else float("nan")
        row["goals_per_sot"] = row["goals_for_per_match"] / max(0.01, row["sot_for_per_match"]) if pd.notna(row["sot_for_per_match"]) else float("nan")
        row["sot_rate"] = row["sot_for_per_match"] / max(0.01, row["shots_for_per_match"]) if pd.notna(row["shots_for_per_match"]) else float("nan")
        out.append(row)
    return pd.DataFrame(out)


def _scale(series: pd.Series, inverse: bool = False) -> pd.Series:
    vals = pd.to_numeric(series, errors="coerce")
    if vals.nunique(dropna=True) <= 1:
        score = pd.Series(50.0, index=series.index)
    else:
        score = vals.rank(pct=True) * 100
    if inverse:
        score = 100 - score
    return score.fillna(50.0).clip(0, 100)


def _reliability(row: pd.Series, required: list[str]) -> tuple[str, str]:
    missing = [col for col in required if pd.isna(row.get(col))]
    if int(row.get("recent_matches_used", 0)) < 6:
        return "Low", "Fewer than 6 prior matches; proxy adjustment should be reduced."
    if missing:
        return "Low", "Missing columns weaken this proxy: " + ", ".join(missing)
    if pd.isna(row.get("market_implied_strength_per_match")):
        return "Medium", "Odds missing; market-implied strength not used."
    return "High", "Basic match-stat sample is sufficient for a proxy, not true event style."


def build_free_style_proxies(matches: pd.DataFrame | str | Path, as_of_date: str) -> pd.DataFrame:
    ratings = build_current_team_ratings(matches, as_of_date)
    if ratings.empty:
        return ratings
    r = ratings.copy()
    r["control_proxy"] = (0.45 * _scale(r["shot_share"]) + 0.35 * _scale(r["corner_share"]) + 0.20 * _scale(r["market_implied_strength_per_match"]))
    r["attacking_pressure_proxy"] = (0.35 * _scale(r["shots_for_per_match"]) + 0.30 * _scale(r["sot_for_per_match"]) + 0.20 * _scale(r["corners_for_per_match"]) + 0.15 * _scale(r["goals_for_per_match"]))
    r["defensive_shell_proxy"] = (0.30 * _scale(r["shots_against_per_match"], inverse=True) + 0.30 * _scale(r["sot_against_per_match"], inverse=True) + 0.25 * _scale(r["goals_against_per_match"], inverse=True) + 0.15 * _scale(r["total_shots_per_match"], inverse=True))
    r["tempo_proxy"] = (0.35 * _scale(r["total_shots_per_match"]) + 0.25 * _scale(r["total_corners_per_match"]) + 0.25 * _scale(r["total_goals_per_match"]) + 0.15 * _scale(r["total_cards_fouls_per_match"]))
    r["chaos_proxy"] = (0.45 * _scale(r["total_cards_fouls_per_match"]) + 0.25 * _scale(r["red_cards_per_match"]) + 0.15 * _scale(r["total_goals_per_match"]) + 0.15 * _scale((r["shots_for_per_match"] - r["shots_against_per_match"]).abs()))
    r["finishing_proxy"] = (0.55 * _scale(r["goals_per_shot"]) + 0.45 * _scale(r["goals_per_sot"]))
    r["chance_quality_proxy"] = (0.60 * _scale(r["sot_rate"]) + 0.40 * _scale(r["goals_per_shot"]))
    r["directness_proxy"] = (0.55 * r["attacking_pressure_proxy"] + 0.45 * (100 - r["control_proxy"])).clip(0, 100)
    r["under_profile_proxy"] = (0.35 * _scale(r["total_shots_per_match"], inverse=True) + 0.30 * _scale(r["total_goals_per_match"], inverse=True) + 0.20 * _scale(r["sot_against_per_match"], inverse=True) + 0.15 * (100 - r["tempo_proxy"]))

    for proxy in PROXY_NAMES:
        vals = pd.to_numeric(r[proxy], errors="coerce")
        std = vals.std(ddof=0)
        r[f"{proxy}_z"] = 0.0 if std == 0 or pd.isna(std) else (vals - vals.mean()) / std
        r[f"{proxy}_percentile"] = _scale(vals)
        labels = r.apply(lambda row: _reliability(row, ["shots_for_per_match", "sot_for_per_match", "corners_for_per_match"]), axis=1)
        r[f"{proxy}_reliability"] = [x[0] for x in labels]
        r[f"{proxy}_warning"] = [x[1] for x in labels]
        r[f"{proxy}_evidence"] = r.apply(lambda row: f"matches={row['recent_matches_used']}; shots_for={row.get('shots_for_per_match', np.nan):.2f}; shots_against={row.get('shots_against_per_match', np.nan):.2f}; corners_for={row.get('corners_for_per_match', np.nan):.2f}; data_mode=free_proxy_style", axis=1)
    r["data_mode"] = "free_proxy_style"
    r["data_quality_flags"] = r.apply(lambda row: "low_sample" if row["recent_matches_used"] < 6 else "proxy_basic_match_stats", axis=1)
    return r
