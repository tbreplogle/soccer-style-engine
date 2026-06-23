from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.features.free_style_proxies import build_current_team_ratings


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    return data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)


def current_baseline_expected_goals(
    matches: pd.DataFrame | str | Path,
    home_team: str,
    away_team: str,
    as_of_date: str,
    neutral_site: bool = False,
) -> dict[str, float | int]:
    data = _load(matches)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    prior = data[data["date"] < pd.to_datetime(as_of_date)].copy()
    if prior.empty:
        return {"home_xg_base": 1.35, "away_xg_base": 1.10, "home_prior_matches": 0, "away_prior_matches": 0}
    ratings = build_current_team_ratings(prior, as_of_date)
    lookup = ratings.set_index("team")
    league_avg = float(pd.to_numeric(pd.concat([prior["home_goals"], prior["away_goals"]]), errors="coerce").mean())
    league_avg = max(0.2, league_avg)
    home = lookup.loc[home_team] if home_team in lookup.index else pd.Series(dtype=float)
    away = lookup.loc[away_team] if away_team in lookup.index else pd.Series(dtype=float)
    home_attack = float(home.get("goals_for_per_match", league_avg) if pd.notna(home.get("goals_for_per_match", league_avg)) else league_avg)
    away_attack = float(away.get("goals_for_per_match", league_avg) if pd.notna(away.get("goals_for_per_match", league_avg)) else league_avg)
    home_def = float(home.get("goals_against_per_match", league_avg) if pd.notna(home.get("goals_against_per_match", league_avg)) else league_avg)
    away_def = float(away.get("goals_against_per_match", league_avg) if pd.notna(away.get("goals_against_per_match", league_avg)) else league_avg)
    home_adv = 0.12 if not neutral_site else 0.0
    return {
        "home_xg_base": round(max(0.15, 0.58 * home_attack + 0.42 * away_def + home_adv), 4),
        "away_xg_base": round(max(0.15, 0.58 * away_attack + 0.42 * home_def - home_adv / 2), 4),
        "home_prior_matches": int(home.get("recent_matches_used", 0) if not home.empty else 0),
        "away_prior_matches": int(away.get("recent_matches_used", 0) if not away.empty else 0),
    }
