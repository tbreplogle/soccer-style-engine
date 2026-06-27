from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import TEAM_MATCH_STYLE_LOG_PATH


def _load_style_log(style_log: pd.DataFrame | str | Path | None = None) -> pd.DataFrame:
    if style_log is None:
        return pd.read_csv(TEAM_MATCH_STYLE_LOG_PATH)
    if isinstance(style_log, pd.DataFrame):
        return style_log.copy()
    return pd.read_csv(style_log)


def baseline_expected_goals(
    home_team: str,
    away_team: str,
    as_of_date: str,
    style_log: pd.DataFrame | str | Path | None = None,
) -> dict[str, float | int | str]:
    """Estimate baseline xG from only prior matches.

    Uses xG columns when present, otherwise falls back to goals. This is a
    conservative transparent strength model, not a black-box projection.
    """
    log = _load_style_log(style_log)
    log["date"] = pd.to_datetime(log["date"], errors="coerce")
    prior = log[log["date"] < pd.to_datetime(as_of_date)].copy()
    if prior.empty:
        return {
            "home_xg_base": 1.35,
            "away_xg_base": 1.10,
            "home_prior_matches": 0,
            "away_prior_matches": 0,
            "league_home_advantage": 0.15,
        }

    goals_for = "xg_for" if "xg_for" in prior.columns and prior["xg_for"].notna().any() else "goals_for"
    goals_against = "xg_against" if "xg_against" in prior.columns and prior["xg_against"].notna().any() else "goals_against"
    league_for = float(pd.to_numeric(prior[goals_for], errors="coerce").mean())
    league_against = float(pd.to_numeric(prior[goals_against], errors="coerce").mean())
    league_avg = max(0.05, (league_for + league_against) / 2)
    home_rows = prior[prior["team"].eq(home_team)]
    away_rows = prior[prior["team"].eq(away_team)]
    home_attack = float(pd.to_numeric(home_rows[goals_for], errors="coerce").mean()) if not home_rows.empty else league_avg
    home_defense_allowed = float(pd.to_numeric(home_rows[goals_against], errors="coerce").mean()) if not home_rows.empty else league_avg
    away_attack = float(pd.to_numeric(away_rows[goals_for], errors="coerce").mean()) if not away_rows.empty else league_avg
    away_defense_allowed = float(pd.to_numeric(away_rows[goals_against], errors="coerce").mean()) if not away_rows.empty else league_avg
    home_advantage = 0.12
    home_xg = (0.58 * home_attack + 0.42 * away_defense_allowed) + home_advantage
    away_xg = (0.58 * away_attack + 0.42 * home_defense_allowed) - home_advantage / 2
    return {
        "home_xg_base": round(max(0.05, home_xg), 4),
        "away_xg_base": round(max(0.05, away_xg), 4),
        "home_prior_matches": int(home_rows["match_id"].nunique()),
        "away_prior_matches": int(away_rows["match_id"].nunique()),
        "league_home_advantage": home_advantage,
    }
