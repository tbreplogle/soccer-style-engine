from __future__ import annotations

STYLE_METRIC_FORMULAS = {
    "possession_pct": "team possession-team event share; proxy until possession duration is available",
    "field_tilt_pct": "team share of possession events with x >= 80",
    "avg_possession_length": "average seconds between first and last event in a possession",
    "direct_speed": "mean positive x progression per pass/carry event; event-only proxy",
    "progressive_passes": "completed passes advancing at least 10 StatsBomb x units",
    "progressive_carries": "carries advancing at least 10 StatsBomb x units",
    "final_third_entries": "pass/carry endpoints entering x >= 80 from outside",
    "box_entries": "pass/carry endpoints entering x >= 102 and y between 18 and 62",
    "runs_behind_proxy": "through balls or passes into the box; not true tracking data",
    "fast_attack_count": "possessions <=15 seconds ending in a shot or box entry",
    "ppda_proxy": "opponent pass count divided by high defensive actions",
    "defensive_block_height": "median x location of defensive events; 360 median line height when available",
}


def metric_formula(metric: str) -> str:
    return STYLE_METRIC_FORMULAS.get(metric, "Metric formula not yet documented.")
