from __future__ import annotations

import csv
from pathlib import Path

from src.data_sources.source_result import SourceResult
from src.international_current.current_international_schema import CurrentInternationalTeamRating
from src.international_current.team_name_normalization import normalize_team_name


DEFAULT_ELORATINGS_SAMPLE = Path("data/sample/eloratings_sample.csv")


def parse_eloratings(path: str | Path) -> list[CurrentInternationalTeamRating]:
    ratings = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            normalized = normalize_team_name(str(row.get("team") or row.get("Team") or ""))
            ratings.append(CurrentInternationalTeamRating(
                source_name=str(row.get("source_name") or "eloratings"),
                team=normalized.normalized_name,
                rating_value=float(row["rating_value"]) if row.get("rating_value") else None,
                rating_type=str(row.get("rating_type") or "elo"),
                rating_date=str(row.get("rating_date") or ""),
                rank=int(row["rank"]) if row.get("rank") else None,
                matches_played=int(row["matches_played"]) if row.get("matches_played") else None,
                source_url=str(row.get("source_url") or ""),
                reliability_status="local_sample_or_cache",
                warnings=list(dict.fromkeys([
                    "EloRatings is a strength prior only, not style/event data.",
                    normalized.warning,
                ])) if normalized.warning else ["EloRatings is a strength prior only, not style/event data."],
            ))
    return ratings


def audit_eloratings_current(
    cache_path: str | Path = "data/source_cache/eloratings/eloratings_current.csv",
    allow_network: bool = False,
    use_sample_fallback: bool = False,
) -> tuple[SourceResult, list[CurrentInternationalTeamRating]]:
    path = Path(cache_path)
    source_path = path
    fallback_used = False
    if not source_path.exists() and use_sample_fallback and DEFAULT_ELORATINGS_SAMPLE.exists():
        source_path = DEFAULT_ELORATINGS_SAMPLE
        fallback_used = True
    if source_path.exists():
        ratings = parse_eloratings(source_path)
        return SourceResult(
            source_name="eloratings",
            status="success",
            rows_returned=len(ratings),
            fields_available=["team", "rating_value", "rating_type", "rating_date", "rank"],
            competitions_found=["international"],
            date_min=min([rating.rating_date for rating in ratings if rating.rating_date], default=""),
            date_max=max([rating.rating_date for rating in ratings if rating.rating_date], default=""),
            currentness_status="available_sample_ratings" if fallback_used else "available_local_cache",
            coverage_status="national_team_strength_ratings",
            reliability_status="committed_sample" if fallback_used else "local_cache",
            cache_path=str(source_path),
            data_mode="current_strength_rating",
            warnings=[
                "EloRatings are strength priors only and are not style-aware matchup inputs.",
                "Using committed sample ratings." if fallback_used else "Using local ratings cache.",
            ],
        ), ratings
    warning = "EloRatings local cache not found."
    if allow_network:
        warning += " Network fetching can be added behind allow_network if a safe no-key source URL is configured."
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
