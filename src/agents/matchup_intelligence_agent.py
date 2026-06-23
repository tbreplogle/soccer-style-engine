from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.agents.team_identity_agent import classify_team_identity
from src.features.team_aggregates import build_team_style_profile


def _raw(profile: dict[str, Any], metric: str) -> float:
    value = profile.get("raw_metrics", {}).get(metric, 0)
    return float(value) if pd.notna(value) else 0.0


def _edge(text: str, value: float, threshold: float = 0.0) -> str | None:
    return text if abs(value) > threshold else None


def analyze_matchup(
    home_team: str,
    away_team: str,
    as_of_date: str,
    style_log: pd.DataFrame | str | Path | None = None,
) -> dict[str, Any]:
    home = build_team_style_profile(home_team, as_of_date, style_log=style_log)
    away = build_team_style_profile(away_team, as_of_date, style_log=style_log)
    home_id = classify_team_identity(home)["identities"][0]
    away_id = classify_team_identity(away)["identities"][0]

    home_edges = []
    away_edges = []
    checks = [
        ("possession control vs defensive block", "possession_pct", "defensive_block_height"),
        ("vertical pace vs block depth", "direct_speed", "defensive_block_height"),
        ("press vs buildup security", "pressures", "turnovers_own_third"),
        ("transition threat vs turnover profile", "fast_attack_count", "turnovers_middle_third"),
        ("field tilt vs territory resistance", "field_tilt_pct", "field_tilt_pct"),
        ("set-piece strength vs weakness", "set_piece_xg_for", "set_piece_xg_against"),
        ("chance quality vs suppression", "xg_for", "xg_against"),
    ]
    for label, attack_metric, defense_metric in checks:
        home_signal = _raw(home, attack_metric) - _raw(away, defense_metric)
        away_signal = _raw(away, attack_metric) - _raw(home, defense_metric)
        h = _edge(f"{label}: {home_team} signal {home_signal:.2f}", home_signal, 0.2)
        a = _edge(f"{label}: {away_team} signal {away_signal:.2f}", away_signal, 0.2)
        if h:
            home_edges.append(h)
        if a:
            away_edges.append(a)

    tempo_score = (_raw(home, "direct_speed") + _raw(away, "direct_speed") + _raw(home, "fast_attack_count") + _raw(away, "fast_attack_count")) / 4
    block_drag = (max(0, 60 - _raw(home, "defensive_block_height")) + max(0, 60 - _raw(away, "defensive_block_height"))) / 2
    if tempo_score - block_drag > 3:
        total_pressure = "Up"
    elif block_drag - tempo_score > 3:
        total_pressure = "Down"
    else:
        total_pressure = "Neutral"

    uncertainties = []
    for team, profile in [(home_team, home), (away_team, away)]:
        if int(profile["matches_used"]) < 5:
            uncertainties.append(f"{team}: fewer than 5 prior matches.")
        if "event_only" in str(profile["data_quality_summary"]):
            uncertainties.append(f"{team}: no 360/tracking context in recent sample.")
    uncertainties.append("Recent lineup changes are not measured in this phase.")

    return {
        "home_team": home_team,
        "away_team": away_team,
        "as_of_date": as_of_date,
        "style_summary": f"{home_team}: {home_id['label']} vs {away_team}: {away_id['label']}",
        "home_style_edges": home_edges or ["No strong measured style edge."],
        "away_style_edges": away_edges or ["No strong measured style edge."],
        "total_goals_style_pressure": total_pressure,
        "projected_game_script": _game_script(home_team, away_team, home, away),
        "key_uncertainties": uncertainties,
        "data_quality_flags": [str(home["data_quality_summary"]), str(away["data_quality_summary"])],
    }


def _game_script(home_team: str, away_team: str, home: dict[str, Any], away: dict[str, Any]) -> str:
    control_gap = _raw(home, "possession_pct") - _raw(away, "possession_pct")
    if control_gap >= 8:
        return f"{home_team} likely has more ball/territory; {away_team} may defend longer spells and look for transition moments."
    if control_gap <= -8:
        return f"{away_team} likely has more ball/territory; {home_team} may defend longer spells and look for transition moments."
    return "Possession control is not clearly separated; game script should stay neutral until stronger evidence appears."
