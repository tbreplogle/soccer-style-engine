from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.data_sources.source_result import SourceResult
from src.international_current.current_international_schema import CurrentInternationalFixture


def _status(value: str | None) -> str:
    text = str(value or "").lower()
    if text in {"scheduled", "live", "complete", "postponed"}:
        return text
    return "unknown"


def parse_openfootball_fixtures(path: str | Path) -> list[CurrentInternationalFixture]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    matches = data.get("matches", data if isinstance(data, list) else [])
    fixtures = []
    for index, row in enumerate(matches):
        home = row.get("home_team") or row.get("team1") or row.get("home")
        away = row.get("away_team") or row.get("team2") or row.get("away")
        fixtures.append(CurrentInternationalFixture(
            source_name="openfootball_worldcup",
            source_match_id=str(row.get("id") or row.get("source_match_id") or index),
            competition=str(row.get("competition") or data.get("competition", "FIFA World Cup")),
            season=str(row.get("season") or data.get("season", "")),
            match_date=str(row.get("match_date") or row.get("date") or ""),
            kickoff_time=str(row.get("kickoff_time") or row.get("time") or ""),
            home_team=str(home or ""),
            away_team=str(away or ""),
            neutral_site=str(row.get("neutral_site", "true")),
            venue=str(row.get("venue") or ""),
            status=_status(row.get("status")),
            home_score=row.get("home_score"),
            away_score=row.get("away_score"),
            round_name=str(row.get("round_name") or row.get("round") or ""),
            group_name=str(row.get("group_name") or row.get("group") or ""),
            source_url=str(row.get("source_url") or ""),
            reliability_status="local_sample_or_cache",
            warnings=["OpenFootball fixture source provides schedule/results only."],
        ))
    return fixtures


def audit_openfootball_worldcup(cache_path: str | Path = "data/source_cache/openfootball_worldcup.json", allow_network: bool = False) -> tuple[SourceResult, list[CurrentInternationalFixture]]:
    path = Path(cache_path)
    if path.exists():
        fixtures = parse_openfootball_fixtures(path)
        return SourceResult(
            source_name="openfootball_worldcup",
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
            warnings=["OpenFootball is fixture/result structure only; no xG, lineups, or style data."],
        ), fixtures
    warning = "OpenFootball local cache not found."
    if allow_network:
        warning += " Network fetching is planned but not implemented in Phase 22."
    return SourceResult(
        source_name="openfootball_worldcup",
        status="skipped",
        fields_missing=["fixtures", "scores", "rounds", "groups"],
        currentness_status="not_checked_no_local_cache",
        coverage_status="no_local_fixture_backbone",
        reliability_status="planned",
        warnings=[warning],
        cache_path=str(path),
        data_mode="unavailable",
    ), []
