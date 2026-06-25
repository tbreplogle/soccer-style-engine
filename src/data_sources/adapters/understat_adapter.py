from __future__ import annotations

from src.data_sources.adapters.planned_adapters import planned_source_probe


def audit_understat(allow_network: bool = False):
    return planned_source_probe("understat", allow_network=allow_network)
