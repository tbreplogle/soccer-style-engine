from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_sources.adapters.eloratings_adapter import audit_eloratings_current, parse_eloratings
from src.international_current.current_international_schema import CurrentInternationalTeamRating
from src.international_current.fixture_harvest import SourceAuditRow
from src.international_current.team_name_normalization import normalize_team_name


RATING_COLUMNS = [
    "team_name",
    "normalized_team_name",
    "rating",
    "rating_source",
    "rating_date",
    "source_status",
    "confidence",
    "warning",
]


def _is_sample_path(path: Path) -> bool:
    return "sample" in [part.lower() for part in path.parts]


def _parse_rating_cache(path: Path) -> list[CurrentInternationalTeamRating]:
    if path.name == "eloratings_current.csv":
        return parse_eloratings(path)
    ratings = []
    sample = _is_sample_path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw = row.get("team_name") or row.get("team") or row.get("Team") or ""
            normalized = normalize_team_name(raw)
            ratings.append(CurrentInternationalTeamRating(
                source_name=row.get("rating_source") or row.get("source_name") or "local_current_international_rating_cache",
                team=normalized.normalized_name,
                rating_value=float(row["rating"]) if row.get("rating") else float(row["rating_value"]) if row.get("rating_value") else None,
                rating_type=row.get("rating_type") or "elo",
                rating_date=row.get("rating_date") or "",
                rank=int(row["rank"]) if row.get("rank") else None,
                source_url=row.get("source_url") or "",
                reliability_status="sample_only" if sample else row.get("reliability_status") or "local_cache",
                source_tier="sample" if sample else row.get("source_tier") or "real",
                is_sample_data=sample,
                warnings=list(dict.fromkeys([
                    normalized.warning,
                    row.get("warning") or "",
                    "Rating is a strength prior only, not a style advantage.",
                ])),
            ))
    return ratings


def _rating_frame(ratings: list[CurrentInternationalTeamRating]) -> pd.DataFrame:
    rows = []
    for rating in ratings:
        rows.append({
            "team_name": rating.team,
            "normalized_team_name": rating.team,
            "rating": rating.rating_value,
            "rating_source": rating.source_name,
            "rating_date": rating.rating_date,
            "source_status": rating.reliability_status,
            "confidence": "sample" if rating.is_sample_data else "high" if rating.rating_value is not None else "missing",
            "warning": " | ".join(w for w in rating.warnings if w),
        })
    frame = pd.DataFrame(rows)
    for column in RATING_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[RATING_COLUMNS]


def harvest_current_international_ratings(
    *,
    fixture_teams: list[str] | None = None,
    allow_network: bool = False,
    cache_dir: str | Path = "data/source_cache/current_international",
    allow_sample_data: bool = False,
) -> dict[str, Any]:
    cache = Path(cache_dir)
    audit_rows: list[SourceAuditRow] = []
    ratings: list[CurrentInternationalTeamRating] = []
    local_path = cache / "parsed" / "ratings.csv"
    if not local_path.exists():
        local_path = cache / "ratings.csv"
    if local_path.exists() and (allow_sample_data or not _is_sample_path(local_path)):
        try:
            ratings.extend(_parse_rating_cache(local_path))
            audit_rows.append(SourceAuditRow(
                source_name="local_current_international_rating_cache",
                source_type="rating",
                attempted=True,
                success=True,
                row_count=len(ratings),
                coverage_count=len(ratings),
                cache_path=str(local_path),
                freshness_date=datetime.fromtimestamp(local_path.stat().st_mtime, tz=timezone.utc).date().isoformat(),
                recommendation="Use local rating cache.",
            ))
        except Exception as exc:
            audit_rows.append(SourceAuditRow(
                source_name="local_current_international_rating_cache",
                source_type="rating",
                attempted=True,
                error_message=str(exc),
                cache_path=str(local_path),
                recommendation="Fix or refresh rating cache.",
            ))
    else:
        audit_rows.append(SourceAuditRow(
            source_name="local_current_international_rating_cache",
            source_type="rating",
            attempted=True,
            skipped=True,
            cache_path=str(local_path),
            recommendation="Create local ratings cache or allow sample data for demos.",
        ))

    if Path(cache_dir) == Path("data/source_cache/current_international"):
        elo_result, elo_ratings = audit_eloratings_current(allow_network=allow_network, use_sample_fallback=allow_sample_data)
        existing = {rating.team for rating in ratings}
        for rating in elo_ratings:
            if rating.team not in existing:
                ratings.append(rating)
        audit_rows.append(SourceAuditRow(
            source_name="eloratings",
            source_type="rating",
            attempted=True,
            success=bool(elo_ratings),
            skipped=elo_result.status == "skipped",
            row_count=len(elo_ratings),
            coverage_count=len(elo_ratings),
            error_message="; ".join(elo_result.errors),
            cache_path=elo_result.cache_path,
            freshness_date=elo_result.date_max,
            recommendation="Use as strength prior only." if elo_ratings else "No Elo cache available.",
        ))
    else:
        audit_rows.append(SourceAuditRow(
            source_name="eloratings",
            source_type="rating",
            attempted=False,
            skipped=True,
            recommendation="Skipped global Elo cache because a custom cache_dir was supplied.",
        ))

    rating_lookup = {rating.team: rating for rating in ratings if rating.team}
    missing = []
    for raw_team in fixture_teams or []:
        normalized = normalize_team_name(raw_team)
        if normalized.normalized_name not in rating_lookup:
            missing.append(normalized.normalized_name)

    for source_name in ["international-football.net_elo_table"]:
        audit_rows.append(SourceAuditRow(
            source_name=source_name,
            source_type="rating",
            attempted=allow_network,
            skipped=not allow_network,
            recommendation="Network parser not enabled; keep as secondary rating ladder candidate.",
        ))

    return {
        "ratings": ratings,
        "ratings_frame": _rating_frame(ratings),
        "audit_frame": pd.DataFrame([row.to_dict() for row in audit_rows]),
        "missing_rating_teams": sorted(set(missing)),
    }
