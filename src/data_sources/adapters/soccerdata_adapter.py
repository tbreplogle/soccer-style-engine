from __future__ import annotations

from src.data_sources.source_result import SourceResult


SOCCERDATA_READERS = ["FootballData", "ClubElo", "FBref", "Sofascore", "Understat", "WhoScored"]


def audit_soccerdata(allow_network: bool = False) -> SourceResult:
    try:
        import soccerdata as sd  # type: ignore
    except Exception:
        return SourceResult(
            source_name="soccerdata",
            status="skipped",
            fields_missing=SOCCERDATA_READERS,
            currentness_status="not_checked",
            coverage_status="optional_dependency_missing",
            reliability_status="not_installed",
            warnings=["Optional dependency soccerdata is not installed; install separately before probing wrappers."],
            data_mode="unavailable",
        )
    available = [reader for reader in SOCCERDATA_READERS if hasattr(sd, reader)]
    if not allow_network:
        return SourceResult(
            source_name="soccerdata",
            status="skipped",
            fields_available=available,
            fields_missing=[reader for reader in SOCCERDATA_READERS if reader not in available],
            currentness_status="not_checked_no_network",
            coverage_status="wrapper_available_no_network_probe",
            reliability_status="optional_wrapper_present",
            warnings=["soccerdata is installed, but network probing was not allowed."],
            data_mode="unavailable",
        )
    return SourceResult(
        source_name="soccerdata",
        status="warn",
        fields_available=available,
        fields_missing=[reader for reader in SOCCERDATA_READERS if reader not in available],
        currentness_status="network_probe_not_implemented",
        coverage_status="wrapper_probe_planned",
        reliability_status="planned_probe",
        warnings=["Network probing is intentionally conservative in Phase 21; no live soccerdata calls were made."],
        data_mode="unavailable",
    )
