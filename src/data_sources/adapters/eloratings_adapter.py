from __future__ import annotations

import csv
from pathlib import Path

from src.data_sources.source_result import SourceResult
from src.international_current.current_international_schema import CurrentInternationalTeamRating


def parse_eloratings(path: str | Path) -> list[CurrentInternationalTeamRating]:
    ratings = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ratings.append(CurrentInternationalTeamRating(
                source_name="eloratings",
                team=str(row.get("team") or row.get("Team") or ""),
                rating_value=float(row["rating_value"]) if row.get("rating_value") else None,
                rating_type=str(row.get("rating_type") or "elo"),
                rating_date=str(row.get("rating_date") or ""),
                rank=int(row["rank"]) if row.get("rank") else None,
                matches_played=int(row["matches_played"]) if row.get("matches_played") else None,
                source_url=str(row.get("source_url") or ""),
                reliability_status="local_cache",
                warnings=["EloRatings is a strength prior only, not style/event data."],
            ))
    return ratings


def audit_eloratings_current(cache_path: str | Path = "data/source_cache/eloratings_current.csv", allow_network: bool = False) -> tuple[SourceResult, list[CurrentInternationalTeamRating]]:
    path = Path(cache_path)
    if path.exists():
        ratings = parse_eloratings(path)
        return SourceResult(
            source_name="eloratings",
            status="success",
            rows_returned=len(ratings),
            fields_available=["team", "rating_value", "rating_type", "rating_date", "rank"],
            competitions_found=["international"],
            date_min=min([rating.rating_date for rating in ratings if rating.rating_date], default=""),
            date_max=max([rating.rating_date for rating in ratings if rating.rating_date], default=""),
            currentness_status="available_local_cache",
            coverage_status="national_team_strength_ratings",
            reliability_status="local_cache",
            cache_path=str(path),
            data_mode="current_strength_rating",
        ), ratings
    warning = "EloRatings local cache not found."
    if allow_network:
        warning += " Network fetching is planned but not implemented in Phase 22."
    return SourceResult(
        source_name="eloratings",
        status="skipped",
        fields_missing=["team", "rating_value", "rating_date"],
        currentness_status="not_checked_no_local_cache",
        coverage_status="rating_source_planned",
        reliability_status="planned",
        warnings=[warning, "Manual/current slate can still run without ratings, with lower data support."],
        cache_path=str(path),
        data_mode="unavailable",
    ), []
