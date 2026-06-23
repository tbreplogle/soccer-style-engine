from __future__ import annotations

from typing import Any

import numpy as np


INDIVIDUAL_ADJUSTMENT_CAP = 0.12
TOTAL_ADJUSTMENT_CAP = 0.30


def _raw(profile: dict[str, Any], metric: str) -> float:
    value = profile.get("raw_metrics", {}).get(metric, 0)
    return float(value) if value is not None and not np.isnan(float(value)) else 0.0


def _pct(profile: dict[str, Any], metric: str) -> float:
    value = profile.get("percentile_ranks", {}).get(metric, 50)
    return float(value) if value is not None else 50.0


def _cap(value: float, cap: float) -> float:
    return max(-cap, min(cap, value))


def style_adjustment_for_team(team_profile: dict[str, Any], opponent_profile: dict[str, Any]) -> tuple[float, list[str]]:
    adjustments: list[tuple[float, str]] = []
    if _pct(team_profile, "xg_for") >= 65 and _pct(opponent_profile, "xg_against") >= 60:
        adjustments.append((0.08, "chance quality vs opponent chance suppression"))
    if _pct(team_profile, "direct_speed") >= 70 and _pct(opponent_profile, "defensive_block_height") >= 70:
        adjustments.append((0.07, "vertical speed against higher defensive line"))
    if _pct(team_profile, "pressures") >= 70 and _pct(opponent_profile, "turnovers_own_third") >= 60:
        adjustments.append((0.06, "pressing against buildup turnovers"))
    if _pct(team_profile, "field_tilt_pct") >= 70 and _pct(opponent_profile, "field_tilt_pct") <= 40:
        adjustments.append((0.05, "territory pressure vs opponent territory resistance"))
    if _raw(team_profile, "set_piece_xg_for") >= 0.20 and _raw(opponent_profile, "set_piece_xg_against") >= 0.15:
        adjustments.append((0.05, "set-piece xG vs opponent set-piece allowance"))
    if _pct(team_profile, "possession_pct") >= 75 and _pct(team_profile, "box_entries") <= 45:
        adjustments.append((-0.04, "possession control with limited box entry evidence"))

    clipped = [(_cap(value, INDIVIDUAL_ADJUSTMENT_CAP), reason) for value, reason in adjustments]
    total = _cap(sum(value for value, _ in clipped), TOTAL_ADJUSTMENT_CAP)
    quality_text = str(team_profile.get("data_quality_summary", "")) + str(opponent_profile.get("data_quality_summary", ""))
    if "event_only" in quality_text or int(team_profile.get("matches_used", 0)) < 5 or int(opponent_profile.get("matches_used", 0)) < 5:
        total *= 0.5
    return round(total, 4), [reason for _, reason in clipped]
