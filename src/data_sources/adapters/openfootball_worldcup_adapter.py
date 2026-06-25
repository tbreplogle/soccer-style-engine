from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.data_sources.source_result import SourceResult
from src.international_current.current_international_schema import CurrentInternationalFixture
from src.international_current.team_name_normalization import normalize_team_pair


DEFAULT_OPENFOOTBALL_SAMPLE = Path("data/sample/worldcup_static_fixtures_openfootball_sample.json")
NO_REAL_FIXTURE_WARNING = "No real current fixture source available. Provide --manual-matchups or run with --allow-sample-data for demo output."


def _is_sample_path(path: Path) -> bool:
    normalized = [part.lower() for part in path.parts]
    return "data" in normalized and "sample" in normalized


def _status(value: str | None) -> str:
    text = str(value or "").lower()
    if text in {"scheduled", "live", "complete", "postponed"}:
        return text
    return "unknown"


def parse_openfootball_fixtures(path: str | Path) -> list[CurrentInternationalFixture]:
    source_path = Path(path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    is_sample = _is_sample_path(source_path)
    matches = data.get("matches", data if isinstance(data, list) else [])
    fixtures = []
    for index, row in enumerate(matches):
        home = row.get("home_team") or row.get("team1") or row.get("home")
        away = row.get("away_team") or row.get("team2") or row.get("away")
        home_norm, away_norm, name_warnings = normalize_team_pair(str(home or ""), str(away or ""))
        has_score = row.get("home_score") is not None or row.get("away_score") is not None
        warnings = [
            "OpenFootball fixture source provides schedule/results only.",
            "Static fixtures are not event, tracking, xG, lineup, injury, rating, or style data.",
            "Scores/results are present." if has_score else "Fixture-only row; scores/results are not present.",
            *name_warnings,
        ]
        if is_sample:
            warnings.insert(0, "Sample fixture data only. Do not treat this as a real current matchup.")
        fixtures.append(CurrentInternationalFixture(
            source_name="openfootball_worldcup",
            source_match_id=str(row.get("id") or row.get("source_match_id") or index),
            competition=str(row.get("competition") or data.get("competition", "FIFA World Cup")),
            season=str(row.get("season") or data.get("season", "")),
            match_date=str(row.get("match_date") or row.get("date") or ""),
            kickoff_time=str(row.get("kickoff_time") or row.get("time") or ""),
            home_team=home_norm,
            away_team=away_norm,
            neutral_site=str(row.get("neutral_site", "true")),
            venue=str(row.get("venue") or ""),
            status=_status(row.get("status")),
            home_score=row.get("home_score"),
            away_score=row.get("away_score"),
            round_name=str(row.get("round_name") or row.get("round") or ""),
            group_name=str(row.get("group_name") or row.get("group") or ""),
            source_url=str(row.get("source_url") or ""),
            reliability_status="sample_only" if is_sample else "local_cache",
            source_tier="sample" if is_sample else "real",
            is_sample_data=is_sample,
            warnings=list(dict.fromkeys(warning for warning in warnings if warning)),
        ))
    return fixtures


def audit_openfootball_worldcup(
    cache_path: str | Path = "data/source_cache/openfootball/openfootball_worldcup.json",
    allow_network: bool = False,
    use_sample_fallback: bool = False,
) -> tuple[SourceResult, list[CurrentInternationalFixture]]:
    path = Path(cache_path)
    source_path = path
    fallback_used = False
    if not source_path.exists() and use_sample_fallback and DEFAULT_OPENFOOTBALL_SAMPLE.exists():
        source_path = DEFAULT_OPENFOOTBALL_SAMPLE
        fallback_used = True
    if source_path.exists():
        fixtures = parse_openfootball_fixtures(source_path)
        has_scores = any(fixture.home_score is not None or fixture.away_score is not None for fixture in fixtures)
        return SourceResult(
            source_name="openfootball_worldcup",
            status="success",
            rows_returned=len(fixtures),
            fields_available=["fixtures", "rounds", "groups"] + (["scores"] if has_scores else []),
            fields_missing=[] if has_scores else ["scores", "match_stats", "xg", "lineups", "style_inputs"],
            competitions_found=sorted({fixture.competition for fixture in fixtures if fixture.competition}),
            date_min=min([fixture.match_date for fixture in fixtures if fixture.match_date], default=""),
            date_max=max([fixture.match_date for fixture in fixtures if fixture.match_date], default=""),
            currentness_status="available_sample_fixture_backbone" if fallback_used else "available_local_cache",
            coverage_status="fixture_backbone",
            reliability_status="committed_sample" if fallback_used else "local_cache",
            cache_path=str(source_path),
            data_mode="current_fixture_result" if has_scores else "current_fixture_only",
            warnings=[
                "OpenFootball is fixture/result structure only; no xG, lineups, injuries, or style data.",
                "Using committed sample fixture backbone." if fallback_used else "Using local OpenFootball cache.",
            ],
        ), fixtures
    warning = NO_REAL_FIXTURE_WARNING
    if allow_network:
        warning += " Public OpenFootball/football.db fetch can be added behind allow_network, but no URL is configured in Phase 25."
    return SourceResult(
        source_name="openfootball_worldcup",
        status="skipped",
        fields_missing=["fixtures", "scores", "rounds", "groups", "style_inputs"],
        currentness_status="not_checked_no_local_cache",
        coverage_status="no_local_fixture_backbone",
        reliability_status="missing_local_fixture_cache",
        warnings=[warning],
        cache_path=str(path),
        data_mode="unavailable",
    ), []
