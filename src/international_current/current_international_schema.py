from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


CURRENT_INTERNATIONAL_DATA_MODES = {
    "current_fixture_only",
    "current_fixture_result",
    "current_fixture_stats",
    "current_fixture_xg",
    "current_strength_rating",
    "current_scoreboard_result",
    "manual_current_fixture",
    "fallback_rating_only",
    "unavailable",
}

DATA_SUPPORT_LEVELS = {
    "high_current_fixture_stats_xg",
    "high_current_fixture_stats",
    "medium_current_fixture_rating",
    "medium_current_fixture_scoreboard_rating",
    "low_manual_fixture_rating",
    "low_fixture_only",
    "historical_context_only",
    "insufficient",
    "sample_demo_only",
    "real_fixture_full_rating",
    "real_fixture_partial_rating",
    "real_fixture_missing_rating",
    "real_fixture_basic_stats",
    "real_fixture_xg_stats",
    "manual_fixture_full_rating",
    "manual_fixture_partial_rating",
    "manual_fixture_missing_rating",
    "manual_fixture_basic_stats",
    "manual_fixture_xg_stats",
}


@dataclass
class _DictMixin:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CurrentInternationalFixture(_DictMixin):
    source_name: str
    source_match_id: str = ""
    competition: str = ""
    season: str = ""
    match_date: str = ""
    kickoff_time: str = ""
    home_team: str = ""
    away_team: str = ""
    neutral_site: str = "unknown"
    venue: str = ""
    status: str = "unknown"
    home_score: float | None = None
    away_score: float | None = None
    round_name: str = ""
    group_name: str = ""
    source_url: str = ""
    reliability_status: str = "unknown"
    source_tier: str = "real"
    is_sample_data: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class CurrentInternationalTeamRating(_DictMixin):
    source_name: str
    team: str
    rating_value: float | None = None
    rating_type: str = ""
    rating_date: str = ""
    rank: int | None = None
    matches_played: int | None = None
    source_url: str = ""
    reliability_status: str = "unknown"
    source_tier: str = "real"
    is_sample_data: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class CurrentInternationalMatchStats(_DictMixin):
    source_name: str
    source_match_id: str = ""
    home_team: str = ""
    away_team: str = ""
    possession_home: float | None = None
    possession_away: float | None = None
    shots_home: float | None = None
    shots_away: float | None = None
    shots_on_target_home: float | None = None
    shots_on_target_away: float | None = None
    xg_home: float | None = None
    xg_away: float | None = None
    xgot_home: float | None = None
    xgot_away: float | None = None
    corners_home: float | None = None
    corners_away: float | None = None
    fouls_home: float | None = None
    fouls_away: float | None = None
    cards_home: float | None = None
    cards_away: float | None = None
    lineups_available: bool = False
    player_ratings_available: bool = False
    data_mode: str = "unavailable"
    reliability_status: str = "unknown"
    source_tier: str = "real"
    is_sample_data: bool = False
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.data_mode not in CURRENT_INTERNATIONAL_DATA_MODES:
            raise ValueError(f"Unsupported current international data mode: {self.data_mode}")


@dataclass
class CurrentInternationalSlateRow(_DictMixin):
    match_date: str
    competition: str
    round_name: str
    group_name: str
    home_team: str
    away_team: str
    kickoff_time: str = ""
    neutral_site: str = "unknown"
    source_fixture_status: str = "unknown"
    fixture_source_name: str = ""
    source_fixture_name: str = ""
    rating_source_name: str = ""
    stats_source_name: str = ""
    scoreboard_source_name: str = ""
    data_mode: str = "unavailable"
    data_support_level: str = "insufficient"
    reliability_status: str = "unknown"
    source_tier: str = "real"
    is_sample_data: bool = False
    warnings: str = ""
    style_inputs_available: bool = False
    style_inputs_warning: str = ""
    data_coverage_score: float = 0.0
    missing_data_summary: str = ""
    source_audit_status: str = ""
    fixture_resolution_status: str = "resolved"
    is_resolved_fixture: bool = True
    home_team_resolved: bool = True
    away_team_resolved: bool = True
    placeholder_reason: str = ""
    projection_eligible: bool = True
    projection_skip_reason: str = ""
    fixture_date: str = ""
    kickoff_datetime_utc: str = ""
    fixture_date_status: str = "unknown_date"
    fixture_temporal_status: str = "unknown_date"
    is_current_slate: bool = False
    slate_window_status: str = ""
    slate_skip_reason: str = ""
    slate_window: str = ""
    selected_by_slate_filter: bool = False

    def __post_init__(self) -> None:
        if self.data_support_level not in DATA_SUPPORT_LEVELS:
            raise ValueError(f"Unsupported data support level: {self.data_support_level}")


@dataclass
class CurrentInternationalSourceSummary(_DictMixin):
    source_name: str
    status: str
    current_fixture_coverage: str = "unknown"
    rating_coverage: str = "unknown"
    stats_xg_availability: str = "unknown"
    world_cup_readiness: str = "unknown"
    reliability_status: str = "unknown"
    warnings: list[str] = field(default_factory=list)
