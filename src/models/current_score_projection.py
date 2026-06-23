from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.features.free_style_proxies import build_free_style_proxies
from src.models.current_baseline import current_baseline_expected_goals
from src.models.score_projection import _projection_from_xg

INDIVIDUAL_PROXY_ADJUSTMENT_CAP = 0.08
TOTAL_PROXY_ADJUSTMENT_CAP = 0.20


def _cap(value: float, cap: float) -> float:
    return max(-cap, min(cap, value))


def _proxy_adjustment(team: pd.Series, opponent: pd.Series) -> tuple[float, list[str]]:
    adjustments: list[tuple[float, str]] = []
    if team.get("attacking_pressure_proxy", 50) - opponent.get("defensive_shell_proxy", 50) >= 15:
        adjustments.append((0.06, "attacking_pressure_proxy over opponent defensive_shell_proxy"))
    if team.get("control_proxy", 50) - opponent.get("control_proxy", 50) >= 18:
        adjustments.append((0.04, "control_proxy edge from shots/corners/odds"))
    if team.get("under_profile_proxy", 50) >= 70 or opponent.get("under_profile_proxy", 50) >= 70:
        adjustments.append((-0.05, "under_profile_proxy suppresses total chance volume"))
    if team.get("finishing_proxy", 50) >= 75:
        adjustments.append((0.03, "finishing_proxy is high but unstable"))
    clipped = [(_cap(v, INDIVIDUAL_PROXY_ADJUSTMENT_CAP), reason) for v, reason in adjustments]
    total = _cap(sum(v for v, _ in clipped), TOTAL_PROXY_ADJUSTMENT_CAP)
    if int(team.get("recent_matches_used", 0)) < 6 or int(opponent.get("recent_matches_used", 0)) < 6:
        total *= 0.5
    return round(total, 4), [reason for _, reason in clipped]


def project_current_match(
    matches: pd.DataFrame | str | Path,
    home_team: str,
    away_team: str,
    as_of_date: str,
    league: str | None = None,
    neutral_site: bool = False,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    data = matches.copy() if isinstance(matches, pd.DataFrame) else pd.read_csv(matches)
    if league:
        data = data[data["league"].eq(league)]
    baseline = current_baseline_expected_goals(data, home_team, away_team, as_of_date, neutral_site=neutral_site)
    proxies = build_free_style_proxies(data, as_of_date)
    lookup = proxies.set_index("team")
    home = lookup.loc[home_team] if home_team in lookup.index else pd.Series({"recent_matches_used": 0})
    away = lookup.loc[away_team] if away_team in lookup.index else pd.Series({"recent_matches_used": 0})
    home_adj, home_reasons = _proxy_adjustment(home, away)
    away_adj, away_reasons = _proxy_adjustment(away, home)
    home_final = max(0.05, float(baseline["home_xg_base"]) + home_adj)
    away_final = max(0.05, float(baseline["away_xg_base"]) + away_adj)
    probs = _projection_from_xg(home_final, away_final)
    low_conf = int(baseline["home_prior_matches"]) < 6 or int(baseline["away_prior_matches"]) < 6
    warnings = ["free_proxy_style is not true event/tracking style"]
    if low_conf:
        warnings.append("Fewer than 6 prior matches; proxy adjustments halved.")
    row: dict[str, Any] = {
        "date": as_of_date,
        "home_team": home_team,
        "away_team": away_team,
        "home_xg_base": baseline["home_xg_base"],
        "away_xg_base": baseline["away_xg_base"],
        "home_xg_proxy_adjustment": home_adj,
        "away_xg_proxy_adjustment": away_adj,
        "home_xg_final": round(home_final, 4),
        "away_xg_final": round(away_final, 4),
        **probs,
        "confidence": "Low" if low_conf else "Medium",
        "data_mode": "free_proxy_style",
        "data_quality_flags": "low_sample" if low_conf else "proxy_basic_match_stats",
        "proxy_style_explanation": "; ".join(home_reasons + away_reasons) or "No strong proxy-style adjustment.",
        "warnings": " | ".join(warnings),
    }
    result = pd.DataFrame([row])
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
    return result


def proxy_adjustments_are_capped(matches: pd.DataFrame | str | Path, home_team: str, away_team: str, as_of_date: str) -> bool:
    row = project_current_match(matches, home_team, away_team, as_of_date).iloc[0]
    return abs(row["home_xg_proxy_adjustment"]) <= TOTAL_PROXY_ADJUSTMENT_CAP and abs(row["away_xg_proxy_adjustment"]) <= TOTAL_PROXY_ADJUSTMENT_CAP
