from __future__ import annotations

from src.international_current.current_international_schema import (
    CurrentInternationalFixture,
    CurrentInternationalMatchStats,
    CurrentInternationalSlateRow,
    CurrentInternationalSourceSummary,
    CurrentInternationalTeamRating,
)


def __getattr__(name: str):
    if name in {"audit_current_international_sources", "build_current_international_slate", "project_current_international"}:
        from src.international_current import current_international_slate

        return getattr(current_international_slate, name)
    raise AttributeError(name)

__all__ = [
    "CurrentInternationalFixture",
    "CurrentInternationalMatchStats",
    "CurrentInternationalSlateRow",
    "CurrentInternationalSourceSummary",
    "CurrentInternationalTeamRating",
    "audit_current_international_sources",
    "build_current_international_slate",
    "project_current_international",
]
