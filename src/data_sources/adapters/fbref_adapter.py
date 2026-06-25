from __future__ import annotations

from src.data_sources.adapters.planned_adapters import planned_source_probe


def audit_fbref(allow_network: bool = False):
    return planned_source_probe("fbref", allow_network=allow_network)


def audit_fbref_international(allow_network: bool = False):
    result = audit_fbref(allow_network=allow_network)
    result.warnings.append("FBref is an aggregate fallback candidate, not the primary live source.")
    return result
