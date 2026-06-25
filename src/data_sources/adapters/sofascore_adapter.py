from __future__ import annotations

from src.data_sources.adapters.planned_adapters import planned_source_probe
from src.international_current.current_international_schema import CurrentInternationalFixture, CurrentInternationalMatchStats


def audit_sofascore(allow_network: bool = False):
    return planned_source_probe("sofascore", allow_network=allow_network)


def audit_sofascore_current_international(allow_network: bool = False):
    result = audit_sofascore(allow_network=allow_network)
    result.warnings.append("SofaScore current international fixture/stat parsing is planned; no Selenium or anti-bot bypass is used.")
    return result, [], []


__all__ = ["CurrentInternationalFixture", "CurrentInternationalMatchStats", "audit_sofascore", "audit_sofascore_current_international"]
