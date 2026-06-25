from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


DATA_MODE_LABELS = {
    "current_results_stats",
    "current_fixture_stats",
    "current_event_proxy",
    "current_strength_rating",
    "historical_event_data",
    "historical_open_data",
    "unavailable",
}


@dataclass
class SourceResult:
    source_name: str
    status: str = "skipped"
    rows_returned: int = 0
    fields_available: list[str] = field(default_factory=list)
    fields_missing: list[str] = field(default_factory=list)
    competitions_found: list[str] = field(default_factory=list)
    date_min: str = ""
    date_max: str = ""
    currentness_status: str = "unknown"
    coverage_status: str = "unknown"
    reliability_status: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_path: str = ""
    cache_path: str = ""
    data_mode: str = "unavailable"

    def __post_init__(self) -> None:
        if self.status not in {"success", "warn", "fail", "skipped"}:
            raise ValueError(f"Unsupported source status: {self.status}")
        if self.data_mode not in DATA_MODE_LABELS:
            raise ValueError(f"Unsupported data mode: {self.data_mode}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
