from __future__ import annotations

import json
from pathlib import Path

from src.data_sources.source_result import SourceResult
from src.international_current.current_international_schema import CurrentInternationalFixture


def parse_thestatsapi_fixtures(path: str | Path) -> list[CurrentInternationalFixture]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    matches = data.get("fixtures", data.get("matches", []))
    fixtures = []
    for index, row in enumerate(matches):
        fixtures.append(CurrentInternationalFixture(
            source_name="thestatsapi_worldcup",
            source_match_id=str(row.get("id") or index),
            competition=str(row.get("competition") or "FIFA World Cup"),
            season=str(row.get("season") or ""),
            match_date=str(row.get("date") or row.get("match_date") or ""),
            kickoff_time=str(row.get("time") or row.get("kickoff_time") or ""),
            home_team=str(row.get("home_team") or row.get("home") or ""),
            away_team=str(row.get("away_team") or row.get("away") or ""),
            neutral_site=str(row.get("neutral_site", "true")),
            venue=str(row.get("venue") or ""),
            status=str(row.get("status") or "unknown").lower(),
            home_score=row.get("home_score"),
            away_score=row.get("away_score"),
            round_name=str(row.get("round_name") or row.get("round") or ""),
            group_name=str(row.get("group_name") or row.get("group") or ""),
            source_url=str(row.get("source_url") or ""),
            reliability_status="local_sample_or_cache",
            warnings=["TheStatsAPI fixture source provides schedule/results only unless extra fields exist."],
        ))
    return fixtures


def audit_thestatsapi_worldcup(cache_path: str | Path = "data/source_cache/thestatsapi_worldcup.json", allow_network: bool = False) -> tuple[SourceResult, list[CurrentInternationalFixture]]:
    path = Path(cache_path)
    if path.exists():
        fixtures = parse_thestatsapi_fixtures(path)
        return SourceResult(
            source_name="thestatsapi_worldcup",
            status="success",
            rows_returned=len(fixtures),
            fields_available=["fixtures", "scores", "rounds", "groups"],
            competitions_found=sorted({fixture.competition for fixture in fixtures if fixture.competition}),
            date_min=min([fixture.match_date for fixture in fixtures if fixture.match_date], default=""),
            date_max=max([fixture.match_date for fixture in fixtures if fixture.match_date], default=""),
            currentness_status="available_local_cache",
            coverage_status="fixture_backbone",
            reliability_status="local_cache",
            cache_path=str(path),
            data_mode="current_fixture_result",
        ), fixtures
    warning = "TheStatsAPI local cache not found."
    if allow_network:
        warning += " Network fetching is planned but not implemented in Phase 22."
    return SourceResult(
        source_name="thestatsapi_worldcup",
        status="skipped",
        fields_missing=["fixtures", "scores", "rounds", "groups"],
        currentness_status="not_checked_no_local_cache",
        coverage_status="no_local_fixture_backbone",
        reliability_status="planned",
        warnings=[warning],
        cache_path=str(path),
        data_mode="unavailable",
    ), []
