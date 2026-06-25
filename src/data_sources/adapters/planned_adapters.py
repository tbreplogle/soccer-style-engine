from __future__ import annotations

from src.data_sources.source_registry import get_source_registry
from src.data_sources.source_result import SourceResult


EXPECTED_FIELDS_BY_SOURCE = {
    "sofascore": ["fixtures", "scores", "standings", "match_stats", "shot_xg", "xgot", "lineups", "player_ratings"],
    "whoscored": ["event_actions", "passes", "shots", "dribbles", "tackles", "zones", "player_team_actions"],
    "fbref": ["standard", "shooting", "passing", "defense", "possession", "team_aggregates", "player_aggregates"],
    "understat": ["club_xg", "shot_level_club_data", "top_league_xg"],
    "clubelo": ["club_rating", "rating_date", "club_name"],
    "eloratings": ["national_team_rating", "rating_date", "team_name", "world_cup_context"],
    "statsbomb_open_data": ["events", "lineups", "matches", "competitions", "historical_xg"],
}


def planned_source_probe(source_name: str, allow_network: bool = False) -> SourceResult:
    registry = get_source_registry()
    meta = registry[source_name]
    fields = EXPECTED_FIELDS_BY_SOURCE.get(source_name, [])
    if source_name == "statsbomb_open_data":
        return SourceResult(
            source_name=source_name,
            status="warn",
            fields_available=fields,
            currentness_status="historical_only",
            coverage_status="historical_open_data_only",
            reliability_status="local_open_data_when_present",
            warnings=["StatsBomb Open Data is historical validation data only for current-data workflows."],
            data_mode="historical_open_data",
        )
    if not allow_network:
        return SourceResult(
            source_name=source_name,
            status="skipped",
            fields_missing=fields,
            currentness_status="not_checked_no_network",
            coverage_status="planned_adapter_shell",
            reliability_status="planned",
            warnings=[f"{source_name} probe is planned; network access was not allowed."],
            data_mode="current_strength_rating" if meta["strength_rating_possible"] else "unavailable",
        )
    return SourceResult(
        source_name=source_name,
        status="warn",
        fields_missing=fields,
        currentness_status="network_probe_not_implemented",
        coverage_status="planned_adapter_shell",
        reliability_status="planned",
        warnings=[f"{source_name} live probe is intentionally not implemented in Phase 21; no fragile scraping was attempted."],
        data_mode="current_strength_rating" if meta["strength_rating_possible"] else "unavailable",
    )
