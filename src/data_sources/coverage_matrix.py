from __future__ import annotations

from typing import Any

import pandas as pd

from src.data_sources.source_registry import get_source_registry


def build_coverage_matrix(audit_results: list[dict[str, Any]] | None = None) -> pd.DataFrame:
    registry = get_source_registry()
    result_by_source = {row["source_name"]: row for row in audit_results or []}
    rows = []
    for key, meta in registry.items():
        result = result_by_source.get(key, {})
        rows.append({
            "source": key,
            "club_current": bool(meta["club_coverage"] and meta["current_data_expected"] and not meta["historical_only"]),
            "international_current": bool(meta["international_coverage"] and meta["current_data_expected"] and not meta["historical_only"]),
            "world_cup_current": bool(meta["world_cup_coverage"] and meta["current_data_expected"] and not meta["historical_only"]),
            "xg": bool(meta["shot_xg_possible"]),
            "event_actions": bool(meta["event_data_possible"]),
            "lineups": bool(meta["lineup_possible"]),
            "odds": bool(meta["odds_possible"]),
            "ratings": bool(meta["strength_rating_possible"]),
            "reliability": result.get("reliability_status", "planned" if meta["requires_network"] else "local"),
            "current_status": result.get("currentness_status", "not_audited"),
            "notes": meta["limitation_notes"],
        })
    return pd.DataFrame(rows)


def recommend_source_stack(use_case: str) -> list[str]:
    recommendations = {
        "club_projection": ["football_data", "clubelo", "understat", "fbref", "sofascore"],
        "international_projection": ["eloratings", "sofascore", "fbref", "espn_scoreboard", "statsbomb_open_data"],
        "world_cup_projection": ["openfootball_worldcup", "thestatsapi_worldcup", "sofascore", "eloratings", "espn_scoreboard", "fbref", "manual_fallback", "statsbomb_open_data"],
        "style_event_proxy": ["whoscored", "sofascore", "fbref", "statsbomb_open_data"],
        "xg_enrichment": ["sofascore", "understat", "fbref", "statsbomb_open_data"],
        "strength_ratings": ["clubelo", "eloratings", "football_data_model_ratings_fallback"],
    }
    if use_case not in recommendations:
        raise ValueError(f"Unsupported source-stack use case: {use_case}")
    return recommendations[use_case]
