from __future__ import annotations

from src.data_sources.adapters.planned_adapters import planned_source_probe


def audit_clubelo(allow_network: bool = False):
    return planned_source_probe("clubelo", allow_network=allow_network)


def audit_eloratings(allow_network: bool = False):
    return planned_source_probe("eloratings", allow_network=allow_network)
