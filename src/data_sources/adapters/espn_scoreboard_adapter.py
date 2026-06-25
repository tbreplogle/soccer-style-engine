from __future__ import annotations

from src.data_sources.source_result import SourceResult
from src.international_current.current_international_schema import CurrentInternationalFixture


def audit_espn_scoreboard(allow_network: bool = False) -> tuple[SourceResult, list[CurrentInternationalFixture]]:
    warning = "ESPN scoreboard fallback is not probed in no-network mode."
    if allow_network:
        warning = "ESPN scoreboard live probe is planned; no unofficial live request was made in Phase 22."
    return SourceResult(
        source_name="espn_scoreboard",
        status="warn" if allow_network else "skipped",
        fields_missing=["fixtures", "scores", "status"],
        currentness_status="network_probe_not_implemented" if allow_network else "not_checked_no_network",
        coverage_status="scoreboard_fallback_planned",
        reliability_status="fallback_unofficial",
        warnings=[warning, "ESPN is a fallback for scores/results only, not xG or style data."],
        data_mode="unavailable",
    ), []
