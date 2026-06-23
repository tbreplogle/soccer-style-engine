from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.features.free_style_proxies import build_free_style_proxies


def analyze_free_proxy_matchup(
    matches: pd.DataFrame | str | Path,
    home_team: str,
    away_team: str,
    as_of_date: str,
) -> dict[str, Any]:
    proxies = build_free_style_proxies(matches, as_of_date)
    lookup = proxies.set_index("team")
    home = lookup.loc[home_team]
    away = lookup.loc[away_team]
    home_edges = []
    away_edges = []
    for metric in ["control_proxy", "attacking_pressure_proxy", "defensive_shell_proxy", "tempo_proxy", "under_profile_proxy"]:
        diff = float(home[metric] - away[metric])
        if diff >= 8:
            home_edges.append(f"{home_team} has stronger {metric}: {home[metric]:.1f} vs {away[metric]:.1f}")
        elif diff <= -8:
            away_edges.append(f"{away_team} has stronger {metric}: {away[metric]:.1f} vs {home[metric]:.1f}")
    avg_tempo = (float(home["tempo_proxy"]) + float(away["tempo_proxy"])) / 2
    under_drag = max(float(home["under_profile_proxy"]), float(away["under_profile_proxy"]))
    pressure = "Up" if avg_tempo >= 62 and under_drag < 68 else "Down" if under_drag >= 70 else "Neutral"
    return {
        "style_proxy_summary": f"{home_team} control_proxy={home['control_proxy']:.1f}; {away_team} control_proxy={away['control_proxy']:.1f}. These are free-data proxies only.",
        "home_proxy_edges": home_edges or ["No clear home proxy edge."],
        "away_proxy_edges": away_edges or ["No clear away proxy edge."],
        "total_goals_proxy_pressure": pressure,
        "key_uncertainties": [
            "No tracking/event-location data in free_proxy_style mode.",
            "Shots/corners/SOT proxies do not prove true possession, movement, or pace.",
        ],
        "data_mode": "free_proxy_style",
        "data_quality_flags": [str(home.get("data_quality_flags", "")), str(away.get("data_quality_flags", ""))],
    }
