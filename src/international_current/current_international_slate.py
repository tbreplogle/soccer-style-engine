from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_sources.adapters.openfootball_worldcup_adapter import NO_REAL_FIXTURE_WARNING
from src.data_sources.source_result import SourceResult
from src.international_current.data_coverage import write_coverage_report
from src.international_current.current_international_schema import (
    CurrentInternationalFixture,
    CurrentInternationalMatchStats,
    CurrentInternationalSlateRow,
    CurrentInternationalSourceSummary,
    CurrentInternationalTeamRating,
)
from src.international_current.fixture_harvest import harvest_current_international_fixtures
from src.international_current.fixture_resolution import (
    PLACEHOLDER_SKIP_WARNING,
    classify_fixture,
    write_fixture_readiness_outputs,
)
from src.international_current.fixture_deduplication import (
    deduplicate_fixtures,
    write_fixture_deduplication_outputs,
)
from src.international_current.rating_harvest import harvest_current_international_ratings
from src.international_current.rating_projection import project_from_fixture_and_ratings
from src.international_current.slate_selection import (
    apply_slate_selection,
    write_slate_selection_outputs,
)
from src.international_current.stat_harvest import harvest_current_international_stats
from src.analysis.poisson_output import write_poisson_outputs
from src.international_current.team_name_normalization import normalize_team_pair
from src.models.international_projection import project_international_match


SLATE_COLUMNS = [
    "match_date",
    "competition",
    "round_name",
    "group_name",
    "home_team",
    "away_team",
    "kickoff_time",
    "neutral_site",
    "source_fixture_status",
    "fixture_source_name",
    "source_fixture_name",
    "rating_source_name",
    "stats_source_name",
    "scoreboard_source_name",
    "data_mode",
    "data_support_level",
    "reliability_status",
    "source_tier",
    "is_sample_data",
    "warnings",
    "style_inputs_available",
    "style_inputs_warning",
    "data_coverage_score",
    "missing_data_summary",
    "source_audit_status",
    "fixture_resolution_status",
    "is_resolved_fixture",
    "home_team_resolved",
    "away_team_resolved",
    "placeholder_reason",
    "projection_eligible",
    "projection_skip_reason",
    "fixture_date",
    "kickoff_datetime_utc",
    "fixture_date_status",
    "fixture_temporal_status",
    "is_current_slate",
    "slate_window_status",
    "slate_skip_reason",
    "slate_window",
    "selected_by_slate_filter",
    "fixture_key",
    "deduplication_status",
    "duplicate_group_id",
    "primary_source",
    "duplicate_sources",
    "dedupe_reason",
    "dedupe_confidence",
    "source_priority_score",
    "source_priority_reason",
]

PROJECTION_COLUMNS = [
    "as_of_date",
    "team_a",
    "team_b",
    "neutral_site",
    "competition_context",
    "projection_profile",
    "baseline_mode_used",
    "team_a_xg_base",
    "team_b_xg_base",
    "team_a_xg_final",
    "team_b_xg_final",
    "projected_total",
    "most_likely_score",
    "team_a_win_prob",
    "draw_prob",
    "team_b_win_prob",
    "confidence_score",
    "confidence_label",
    "risk_flags",
    "international_context_warnings",
    "data_mode",
    "home_rating",
    "away_rating",
    "rating_diff",
    "match_date",
    "fixture_date",
    "kickoff_time",
    "kickoff_datetime_utc",
    "competition",
    "round_name",
    "group_name",
    "current_fixture_data_mode",
    "data_support_level",
    "rating_status",
    "rating_warning",
    "reliability_status",
    "source_tier",
    "is_sample_data",
    "source_fixture_name",
    "fixture_source",
    "rating_source_name",
    "rating_source_home",
    "rating_source_away",
    "stats_source_name",
    "stat_source_home",
    "stat_source_away",
    "scoreboard_source_name",
    "fixture_source_status",
    "current_source_warnings",
    "stat_status",
    "data_coverage_score",
    "missing_data_summary",
    "source_audit_status",
    "phase22_guardrails",
    "style_inputs_available",
    "style_inputs_warning",
    "rating_only_warning",
    "primary_warning",
    "source_warning",
    "style_warning",
    "guardrail_flags",
    "fixture_resolution_status",
    "is_resolved_fixture",
    "projection_eligible",
    "projection_skip_reason",
    "fixture_temporal_status",
    "is_current_slate",
    "slate_window_status",
    "slate_skip_reason",
    "slate_window",
    "selected_by_slate_filter",
    "fixture_key",
    "deduplication_status",
    "primary_source",
    "duplicate_sources",
    "source_priority_score",
]


def _run_dir(output_dir: str | Path, as_of_date: str | None) -> Path:
    run_date = as_of_date or date.today().isoformat()
    return Path(output_dir) / run_date


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["No rows."]
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in frame.iterrows():
        values = [str(row.get(col, "")).replace("|", "\\|").replace("\n", " ") for col in columns]
        lines.append("| " + " | ".join(values) + " |")
    return lines


def _result_frame(results: list[SourceResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        data = result.to_dict()
        for key in ["fields_available", "fields_missing", "competitions_found", "warnings", "errors"]:
            data[key] = "; ".join(map(str, data.get(key) or []))
        rows.append(data)
    return pd.DataFrame(rows)


def parse_manual_current_matchups(path: str | Path) -> list[CurrentInternationalFixture]:
    fixtures: list[CurrentInternationalFixture] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            home = row.get("home_team") or row.get("team_a") or ""
            away = row.get("away_team") or row.get("team_b") or ""
            home, away, name_warnings = normalize_team_pair(home, away)
            fixtures.append(CurrentInternationalFixture(
                source_name=row.get("source_name") or "manual_current_fixture",
                source_match_id=row.get("source_match_id") or f"manual-{index + 1}",
                competition=row.get("competition") or "FIFA World Cup",
                season=row.get("season") or "",
                match_date=row.get("match_date") or row.get("as_of_date") or "",
                kickoff_time=row.get("kickoff_time") or "",
                home_team=home,
                away_team=away,
                neutral_site=row.get("neutral_site") or "unknown",
                venue=row.get("venue") or "",
                status=row.get("status") or "scheduled",
                round_name=row.get("round_name") or "",
                group_name=row.get("group_name") or "",
                source_url=row.get("source_url") or "",
                reliability_status="manual_fallback",
                source_tier="manual",
                is_sample_data=False,
                warnings=[
                    "Manual fixture is user supplied and not source-verified; verify teams, venue, neutral-site status, and kickoff externally.",
                    *name_warnings,
                    row.get("notes") or "No current stats/xG attached to this manual fixture.",
                ],
            ))
    return fixtures


def determine_data_support_level(
    fixture: CurrentInternationalFixture | None = None,
    rating: CurrentInternationalTeamRating | None = None,
    stats: CurrentInternationalMatchStats | None = None,
) -> str:
    if stats and (stats.xg_home is not None or stats.xg_away is not None):
        return "high_current_fixture_stats_xg"
    if stats:
        return "high_current_fixture_stats"
    if fixture and fixture.is_sample_data:
        return "sample_demo_only"
    if fixture:
        if rating:
            if fixture.source_name == "espn_scoreboard":
                return "medium_current_fixture_scoreboard_rating"
            if fixture.source_name == "manual_current_fixture" or fixture.reliability_status == "manual_fallback":
                return "low_manual_fixture_rating"
            return "medium_current_fixture_rating"
        if fixture.source_name == "manual_current_fixture" or fixture.reliability_status == "manual_fallback":
            return "low_manual_fixture_rating"
        return "low_fixture_only"
    if rating:
        return "historical_context_only"
    return "insufficient"


def _fixture_support_label(
    fixture: CurrentInternationalFixture,
    home_rating: CurrentInternationalTeamRating | None,
    away_rating: CurrentInternationalTeamRating | None,
    stats: CurrentInternationalMatchStats | None,
) -> str:
    if fixture.is_sample_data:
        return "sample_demo_only"
    prefix = "manual_fixture" if fixture.source_tier == "manual" or fixture.reliability_status == "manual_fallback" else "real_fixture"
    if stats and (stats.xg_home is not None or stats.xg_away is not None):
        return f"{prefix}_xg_stats"
    if stats:
        return f"{prefix}_basic_stats"
    home_ok = bool(home_rating and home_rating.rating_value is not None)
    away_ok = bool(away_rating and away_rating.rating_value is not None)
    if home_ok and away_ok:
        return f"{prefix}_full_rating"
    if home_ok or away_ok:
        return f"{prefix}_partial_rating"
    return f"{prefix}_missing_rating"


def _fixture_mode(fixture: CurrentInternationalFixture) -> str:
    if fixture.source_name == "manual_current_fixture" or fixture.reliability_status == "manual_fallback":
        return "manual_current_fixture"
    if fixture.source_name == "espn_scoreboard":
        return "current_scoreboard_result"
    if fixture.home_score is not None or fixture.away_score is not None:
        return "current_fixture_result"
    return "current_fixture_only"


def _rating_lookup(ratings: list[CurrentInternationalTeamRating]) -> dict[str, CurrentInternationalTeamRating]:
    return {rating.team: rating for rating in ratings if rating.team}


def _rating_for_fixture(
    fixture: CurrentInternationalFixture,
    ratings: dict[str, CurrentInternationalTeamRating],
) -> tuple[CurrentInternationalTeamRating | None, CurrentInternationalTeamRating | None]:
    return ratings.get(fixture.home_team), ratings.get(fixture.away_team)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _fixture_to_slate_row(
    fixture: CurrentInternationalFixture,
    ratings: dict[str, CurrentInternationalTeamRating],
    stats_lookup: dict[str, CurrentInternationalMatchStats] | None = None,
    allow_sample_data: bool = False,
) -> CurrentInternationalSlateRow:
    home_rating, away_rating = _rating_for_fixture(fixture, ratings)
    rating = home_rating if home_rating and away_rating else home_rating or away_rating
    rating_source = rating.source_name if rating else ""
    stats = (stats_lookup or {}).get(fixture.source_match_id)
    mode = stats.data_mode if stats else _fixture_mode(fixture)
    warnings = list(dict.fromkeys([
        *fixture.warnings,
        *(stats.warnings if stats else ["No current event/tracking data is attached."]),
        "SofaScore/basic stats are not true tracking data." if stats else "No current xG/style claims are made from fixture-only inputs.",
        "Proxy score adjustments remain disabled.",
    ]))
    if fixture.is_sample_data:
        warnings = list(dict.fromkeys([
            "Sample fixture data only. Do not treat this as a real current matchup.",
            *warnings,
        ]))
    resolution = classify_fixture(fixture, allow_sample_data=allow_sample_data)
    if not resolution.projection_eligible and resolution.projection_skip_reason:
        warnings = list(dict.fromkeys([*warnings, resolution.projection_skip_reason]))
    return CurrentInternationalSlateRow(
        match_date=fixture.match_date,
        competition=fixture.competition,
        round_name=fixture.round_name,
        group_name=fixture.group_name,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        kickoff_time=fixture.kickoff_time,
        neutral_site=fixture.neutral_site,
        source_fixture_status=fixture.status,
        fixture_source_name=fixture.source_name,
        source_fixture_name=fixture.source_name,
        rating_source_name=rating_source,
        stats_source_name=stats.source_name if stats else "",
        scoreboard_source_name=fixture.source_name if fixture.source_name in {"espn_scoreboard", "sofascore"} and (fixture.home_score is not None or fixture.away_score is not None) else "",
        data_mode=mode,
        data_support_level=determine_data_support_level(fixture, rating, stats),
        reliability_status=fixture.reliability_status,
        source_tier=fixture.source_tier or ("sample" if fixture.is_sample_data else "manual" if fixture.reliability_status == "manual_fallback" else "real"),
        is_sample_data=fixture.is_sample_data,
        warnings=" | ".join(warnings),
        style_inputs_available=False,
        style_inputs_warning="No current event/xG/tracking/style-aware matchup inputs are available for this slate row.",
        data_coverage_score=0,
        missing_data_summary="",
        source_audit_status="",
        fixture_resolution_status=resolution.fixture_resolution_status,
        is_resolved_fixture=resolution.is_resolved_fixture,
        home_team_resolved=resolution.home_team_resolved,
        away_team_resolved=resolution.away_team_resolved,
        placeholder_reason=resolution.placeholder_reason,
        projection_eligible=resolution.projection_eligible,
        projection_skip_reason=resolution.projection_skip_reason,
        fixture_date=fixture.match_date,
        kickoff_datetime_utc="",
        fixture_date_status="valid_date" if fixture.match_date else "unknown_date",
        fixture_temporal_status="unknown_date",
        is_current_slate=False,
        slate_window_status="",
        slate_skip_reason="",
        slate_window="",
        selected_by_slate_filter=False,
        fixture_key="",
        deduplication_status="unique",
        duplicate_group_id="",
        primary_source=fixture.source_name,
        duplicate_sources="",
        dedupe_reason="",
        dedupe_confidence=0.0,
        source_priority_score=0.0,
        source_priority_reason="",
    )


def _source_summary(results: list[SourceResult], manual_count: int) -> list[CurrentInternationalSourceSummary]:
    summaries = []
    for result in results:
        source = result.source_name
        summaries.append(CurrentInternationalSourceSummary(
            source_name=source,
            status=result.status,
            current_fixture_coverage="available" if result.rows_returned and "fixture" in result.coverage_status else result.coverage_status,
            rating_coverage="available" if source == "eloratings" and result.rows_returned else ("planned" if source == "eloratings" else "not_rating_source"),
            stats_xg_availability=(
                "available"
                if source == "sofascore" and ("xg" in result.fields_available or "match_stats" in result.fields_available)
                else "not_available_current"
                if source in {"openfootball_worldcup", "espn_scoreboard", "eloratings"}
                else "planned_unprobed"
            ),
            world_cup_readiness=result.coverage_status,
            reliability_status=result.reliability_status,
            warnings=result.warnings,
        ))
    summaries.append(CurrentInternationalSourceSummary(
        source_name="manual_current_fixture",
        status="success" if manual_count else "skipped",
        current_fixture_coverage=f"{manual_count} manual fixtures" if manual_count else "no manual fixtures supplied",
        rating_coverage="not_rating_source",
        stats_xg_availability="not_available",
        world_cup_readiness="manual_fallback_available" if manual_count else "manual_fallback_not_used",
        reliability_status="manual_fallback",
        warnings=["Manual fallback is committed sample input only; it is not an automated current source."],
    ))
    return summaries


def _write_source_summary(path: Path, results: list[SourceResult], summaries: list[CurrentInternationalSourceSummary], allow_network: bool) -> Path:
    frame = _result_frame(results)
    summary_frame = pd.DataFrame([summary.to_dict() for summary in summaries])
    if not summary_frame.empty:
        summary_frame["warnings"] = summary_frame["warnings"].apply(lambda values: "; ".join(values or []))
    lines = [
        "# Current International Source Summary",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Network allowed: `{allow_network}`",
        "",
        "## Guardrails",
        "",
        "- Current StatsBomb is not used.",
        "- Fixture-only sources are not treated as true event, xG, tracking, or style data.",
        "- No Selenium, login, CAPTCHA, anti-bot, or paywall bypass is used.",
        "- No betting recommendations are produced.",
        "- Proxy score adjustments remain disabled.",
        "",
        "## Adapter Results",
        "",
    ]
    display_cols = ["source_name", "status", "rows_returned", "currentness_status", "coverage_status", "reliability_status", "data_mode"]
    lines.extend(_markdown_table(frame[display_cols] if not frame.empty else frame))
    lines.extend(["", "## Current International Coverage", ""])
    lines.extend(_markdown_table(summary_frame))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def audit_current_international_sources(
    as_of_date: str | None = None,
    competition: str = "FIFA World Cup",
    manual_matchups: str | Path | None = None,
    allow_network: bool = False,
    allow_sample_data: bool = False,
    output_dir: str | Path = "outputs/current_international",
    cache_dir: str | Path = "data/source_cache/current_international",
    refresh_fixtures: bool = False,
    refresh_ratings: bool = False,
    refresh_stats: bool = False,
    dedupe_fixtures: bool = True,
    dedupe_review_threshold: float = 0.75,
    source_priority_mode: str = "balanced",
) -> dict[str, Any]:
    fixture_harvest = harvest_current_international_fixtures(
        as_of_date=as_of_date or date.today().isoformat(),
        competition=competition,
        allow_network=allow_network or refresh_fixtures,
        cache_dir=cache_dir,
        allow_sample_data=allow_sample_data,
    )
    manual_fixtures = parse_manual_current_matchups(manual_matchups) if manual_matchups else []
    fixtures = [*fixture_harvest["fixtures"], *manual_fixtures]
    if competition:
        fixtures = [fixture for fixture in fixtures if not fixture.competition or competition.lower() in fixture.competition.lower()]

    fixture_teams = sorted({team for fixture in fixtures for team in [fixture.home_team, fixture.away_team] if team})
    rating_harvest = harvest_current_international_ratings(
        fixture_teams=fixture_teams,
        allow_network=allow_network or refresh_ratings,
        cache_dir=cache_dir,
        allow_sample_data=allow_sample_data or bool(manual_matchups),
    )
    stat_harvest = harvest_current_international_stats(
        fixture_teams=fixture_teams,
        allow_network=allow_network or refresh_stats,
        cache_dir=cache_dir,
    )
    ratings = rating_harvest["ratings"]
    source_audit = pd.concat(
        [
            fixture_harvest["audit_frame"],
            rating_harvest["audit_frame"],
            stat_harvest["audit_frame"],
        ],
        ignore_index=True,
    )
    rating_names = {rating.team for rating in ratings if rating.team and rating.rating_value is not None}
    missing_ratings = [team for team in fixture_teams if team not in rating_names]
    real_fixture_count = len([fixture for fixture in fixtures if not fixture.is_sample_data and fixture.source_tier != "manual"])
    manual_fixture_count = len([fixture for fixture in fixtures if fixture.source_tier == "manual" or fixture.reliability_status == "manual_fallback"])
    sample_fixture_count = len([fixture for fixture in fixtures if fixture.is_sample_data or fixture.source_tier == "sample"])
    if real_fixture_count and ratings and not missing_ratings:
        readiness = "ready_fixture_and_rating"
    elif fixtures and fixtures == manual_fixtures:
        readiness = "manual_only"
    elif fixtures:
        readiness = "ready_fixture_only"
    else:
        readiness = "insufficient"
    run_dir = _run_dir(output_dir, as_of_date)
    fixtures_frame = fixture_harvest["fixtures_frame"]
    if manual_fixtures:
        manual_frame = pd.DataFrame([{
            "match_date": fixture.match_date,
            "kickoff_time": fixture.kickoff_time,
            "competition": fixture.competition,
            "round_name": fixture.round_name,
            "group_name": fixture.group_name,
            "home_team": fixture.home_team,
            "away_team": fixture.away_team,
            "neutral_site": fixture.neutral_site,
            "venue": fixture.venue,
            "source_name": fixture.source_name,
            "source_url": fixture.source_url,
            "source_tier": "manual",
            "source_status": fixture.status,
            "is_sample_data": False,
            "reliability_status": fixture.reliability_status,
            "fixture_confidence": "manual",
            "warnings": " | ".join(fixture.warnings),
        } for fixture in manual_fixtures])
            # Ensure manual rows match the fixture harvest frame shape.
        fixtures_frame = pd.concat([fixtures_frame, manual_frame[fixtures_frame.columns]], ignore_index=True) if not fixtures_frame.empty else manual_frame
    coverage_dir = run_dir / "source_audit"
    coverage = write_coverage_report(
        output_dir=coverage_dir,
        source_audit=source_audit,
        fixtures=fixtures_frame,
        ratings=rating_harvest["ratings_frame"],
        stats=stat_harvest["stats_frame"],
    )
    summary_path = Path(coverage["paths"]["source_audit_summary"])
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of_date or date.today().isoformat(),
        "competition": competition,
        "allow_network": allow_network,
        "allow_sample_data": allow_sample_data,
        "fixture_count": len(fixtures),
        "real_fixture_count": real_fixture_count,
        "manual_fixture_count": manual_fixture_count,
        "sample_fixture_count": sample_fixture_count,
        "rating_count": len(ratings),
        "teams_missing_ratings": missing_ratings,
        "teams_missing_ratings_count": len(missing_ratings),
        "world_cup_readiness_status": readiness,
        "style_inputs_available": False,
        "style_inputs_warning": "No current event/xG/tracking/style-aware matchup inputs are available; do not report style-aware projection ready.",
        "stats_count": len(stat_harvest["stats_frame"]),
        "stat_xg_team_count": int(stat_harvest["stats_frame"].get("xg_for_per_match", pd.Series(dtype=object)).notna().sum()) if not stat_harvest["stats_frame"].empty else 0,
        "source_status_counts": source_audit[["success", "skipped", "blocked"]].sum(numeric_only=True).to_dict() if not source_audit.empty else {},
        "guardrails": {
            "current_statsbomb_used": False,
            "the_stats_api_used": False,
            "fixture_only_not_true_style": True,
            "proxy_adjustments_enabled": False,
            "betting_recommendations": False,
        },
        "dedupe_fixtures": dedupe_fixtures,
        "dedupe_review_threshold": dedupe_review_threshold,
        "source_priority_mode": source_priority_mode,
        "output_paths": {"source_summary": str(summary_path), **coverage["paths"]},
        "warnings": [] if fixtures else [NO_REAL_FIXTURE_WARNING],
    }
    manifest_path = _write_json(run_dir / "current_international_manifest.json", manifest)
    return {
        "run_dir": run_dir,
        "results": [],
        "source_summaries": [],
        "source_audit": source_audit,
        "fixtures_frame": fixtures_frame,
        "ratings_frame": rating_harvest["ratings_frame"],
        "stats_frame": stat_harvest["stats_frame"],
        "match_coverage": coverage["match_coverage"],
        "fixtures": fixtures,
        "ratings": ratings,
        "stats": [],
        "source_summary_path": summary_path,
        "source_audit_dir": coverage_dir,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }


def build_current_international_slate(
    as_of_date: str,
    competition: str = "FIFA World Cup",
    manual_matchups: str | Path | None = None,
    allow_network: bool = False,
    allow_sample_data: bool = False,
    output_dir: str | Path = "outputs/current_international",
    cache_dir: str | Path = "data/source_cache/current_international",
    refresh_fixtures: bool = False,
    refresh_ratings: bool = False,
    refresh_stats: bool = False,
    dedupe_fixtures: bool = True,
    dedupe_review_threshold: float = 0.75,
    source_priority_mode: str = "balanced",
) -> dict[str, Any]:
    audit = audit_current_international_sources(
        as_of_date=as_of_date,
        competition=competition,
        manual_matchups=manual_matchups,
        allow_network=allow_network,
        allow_sample_data=allow_sample_data,
        output_dir=output_dir,
        cache_dir=cache_dir,
        refresh_fixtures=refresh_fixtures,
        refresh_ratings=refresh_ratings,
        refresh_stats=refresh_stats,
    )
    ratings = _rating_lookup(audit["ratings"])
    stats_lookup = {stat.source_match_id: stat for stat in audit["stats"] if stat.source_match_id}
    readiness = write_fixture_readiness_outputs(
        run_dir=audit["run_dir"],
        fixtures=audit["fixtures"],
        ratings=ratings,
        allow_sample_data=allow_sample_data,
    )
    rows = [
        _fixture_to_slate_row(fixture, ratings, stats_lookup, allow_sample_data=allow_sample_data).to_dict()
        for fixture in audit["fixtures"]
    ]
    frame = pd.DataFrame(rows)
    for column in SLATE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[SLATE_COLUMNS]
    coverage = audit.get("match_coverage", pd.DataFrame())
    if not frame.empty and not coverage.empty:
        coverage_lookup = {
            (str(row.get("match_date", "")), str(row.get("home_team", "")), str(row.get("away_team", ""))): row
            for _, row in coverage.iterrows()
        }
        scores = []
        missing = []
        for _, row in frame.iterrows():
            item = coverage_lookup.get((str(row.get("match_date", "")), str(row.get("home_team", "")), str(row.get("away_team", ""))))
            if item is None:
                scores.append(0)
                missing.append("coverage_row_missing")
                continue
            scores.append(item.get("data_coverage_score", 0))
            missing.append(item.get("missing_items", ""))
        frame["data_coverage_score"] = scores
        frame["missing_data_summary"] = missing
        frame["source_audit_status"] = audit["manifest"]["world_cup_readiness_status"]
    run_dir = audit["run_dir"]
    dedupe_result = deduplicate_fixtures(
        frame,
        enabled=dedupe_fixtures,
        review_threshold=dedupe_review_threshold,
        source_priority_mode=source_priority_mode,
    )
    dedupe_paths = write_fixture_deduplication_outputs(run_dir=run_dir, dedupe_result=dedupe_result)
    frame = dedupe_result["deduplicated"]
    slate_path = run_dir / "current_international_slate.csv"
    slate_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(slate_path, index=False)
    manifest = dict(audit["manifest"])
    manifest["slate_rows"] = len(frame)
    manifest.update(dedupe_result["summary"])
    manifest["dedupe_fixtures"] = dedupe_fixtures
    manifest["dedupe_review_threshold"] = dedupe_review_threshold
    manifest["source_priority_mode"] = source_priority_mode
    manifest.update(readiness["summary"])
    manifest["output_paths"] = {
        **manifest["output_paths"],
        "slate": str(slate_path),
        "manifest": str(run_dir / "current_international_manifest.json"),
        **readiness["paths"],
        **dedupe_paths,
    }
    if dedupe_result["summary"]["possible_duplicate_review_rows"]:
        manifest["warnings"] = list(dict.fromkeys([
            *manifest.get("warnings", []),
            "Possible neutral-site duplicate fixtures need review before relying on slate counts.",
        ]))
    if readiness["summary"]["skipped_placeholder_rows"]:
        manifest["warnings"] = list(dict.fromkeys([*manifest.get("warnings", []), PLACEHOLDER_SKIP_WARNING]))
    manifest_path = _write_json(run_dir / "current_international_manifest.json", manifest)
    return {
        **audit,
        "slate": frame,
        "slate_path": slate_path,
        "fixture_readiness": readiness["frame"],
        "fixture_readiness_paths": readiness["paths"],
        "fixture_deduplication": dedupe_result,
        "fixture_deduplication_paths": dedupe_paths,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }


def _empty_international_history() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "match_id",
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "match_stage",
        "competition_name",
        "data_mode",
        "has_event_data",
    ])


def _write_projection_report(path: Path, projections: pd.DataFrame, slate: pd.DataFrame) -> Path:
    lines = [
        "# Current International Projection Report",
        "",
        "## Guardrails",
        "",
        "- This report does not use current StatsBomb data.",
        "- Fixture-only/manual inputs are not true event, tracking, xG, lineup, or style data.",
        "- No betting recommendations are produced.",
        "- Proxy score adjustments remain disabled.",
        "",
        "## Projection Summary",
        "",
    ]
    summary_cols = [
        "team_a",
        "team_b",
        "projected_total",
        "most_likely_score",
        "team_a_win_prob",
        "draw_prob",
        "team_b_win_prob",
        "confidence_label",
        "data_support_level",
        "fixture_resolution_status",
        "projection_eligible",
        "fixture_date",
        "fixture_temporal_status",
        "slate_window_status",
        "deduplication_status",
        "primary_source",
    ]
    lines.extend(_markdown_table(projections[summary_cols] if not projections.empty else projections))
    lines.extend(["", "## Current Slate Inputs", ""])
    slate_cols = [
        "match_date",
        "home_team",
        "away_team",
        "source_fixture_name",
        "fixture_resolution_status",
        "projection_eligible",
        "projection_skip_reason",
        "fixture_date",
        "fixture_temporal_status",
        "selected_by_slate_filter",
        "slate_window_status",
        "slate_skip_reason",
        "deduplication_status",
        "primary_source",
        "duplicate_sources",
        "data_mode",
        "data_support_level",
        "warnings",
    ]
    lines.extend(_markdown_table(slate[slate_cols] if not slate.empty else slate))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def project_current_international(
    as_of_date: str,
    competition: str = "FIFA World Cup",
    manual_matchups: str | Path | None = None,
    allow_network: bool = False,
    allow_sample_data: bool = False,
    max_matches: int = 10,
    output_dir: str | Path = "outputs/current_international",
    cache_dir: str | Path = "data/source_cache/current_international",
    refresh_fixtures: bool = False,
    refresh_ratings: bool = False,
    refresh_stats: bool = False,
    source_audit: bool = False,
    strict_real_data: bool = False,
    build_poisson_board: bool = False,
    include_unresolved_fixtures: bool = False,
    resolved_only: bool = True,
    slate_window: str = "default",
    days_ahead: int = 7,
    date_from: str | None = None,
    date_to: str | None = None,
    include_past: bool = False,
    dedupe_fixtures: bool = True,
    dedupe_review_threshold: float = 0.75,
    source_priority_mode: str = "balanced",
) -> dict[str, Any]:
    slate_result = build_current_international_slate(
        as_of_date=as_of_date,
        competition=competition,
        manual_matchups=manual_matchups,
        allow_network=allow_network,
        allow_sample_data=allow_sample_data,
        output_dir=output_dir,
        cache_dir=cache_dir,
        refresh_fixtures=refresh_fixtures,
        refresh_ratings=refresh_ratings,
        refresh_stats=refresh_stats,
        dedupe_fixtures=dedupe_fixtures,
        dedupe_review_threshold=dedupe_review_threshold,
        source_priority_mode=source_priority_mode,
    )
    full_slate = slate_result["slate"].copy()
    slate_selection = apply_slate_selection(
        full_slate,
        as_of_date=as_of_date,
        slate_window=slate_window,
        days_ahead=days_ahead,
        date_from=date_from,
        date_to=date_to,
        include_past=include_past,
    )
    full_slate = slate_selection["annotated_slate"]
    selection_paths = write_slate_selection_outputs(
        run_dir=slate_result["run_dir"],
        annotated_slate=full_slate,
        summary=slate_selection["summary"],
    )
    full_slate.to_csv(slate_result["slate_path"], index=False)
    slate = slate_selection["selected_slate"].head(max_matches).copy()
    ratings = _rating_lookup(slate_result["ratings"])
    rows = []
    for _, matchup in slate.iterrows():
        fixture_matches = [
            fixture for fixture in slate_result["fixtures"]
            if fixture.home_team == str(matchup["home_team"])
            and fixture.away_team == str(matchup["away_team"])
            and fixture.match_date == str(matchup["match_date"])
            and fixture.source_name == str(matchup["source_fixture_name"])
        ]
        if not fixture_matches:
            fixture_matches = [
                fixture for fixture in slate_result["fixtures"]
                if fixture.home_team == str(matchup["home_team"])
                and fixture.away_team == str(matchup["away_team"])
                and fixture.match_date == str(matchup["match_date"])
                and fixture.reliability_status == str(matchup["reliability_status"])
            ]
        fixture = fixture_matches[0] if fixture_matches else CurrentInternationalFixture(
            source_name=str(matchup["source_fixture_name"]),
            match_date=str(matchup["match_date"]),
            competition=str(matchup["competition"]),
            home_team=str(matchup["home_team"]),
            away_team=str(matchup["away_team"]),
            neutral_site=str(matchup["neutral_site"]),
            reliability_status=str(matchup["reliability_status"]),
        )
        home_rating, away_rating = _rating_for_fixture(fixture, ratings)
        baseline = project_from_fixture_and_ratings(fixture, home_rating, away_rating)
        support_label = str(matchup["data_support_level"])
        if strict_real_data or source_audit:
            support_label = _fixture_support_label(fixture, home_rating, away_rating, None)
        row = {
            "as_of_date": as_of_date,
            "team_a": baseline["home_team"],
            "team_b": baseline["away_team"],
            "neutral_site": matchup["neutral_site"],
            "competition_context": matchup["competition"],
            "projection_profile": "current_fixture_rating_baseline",
            "baseline_mode_used": "fixture_rating_only_baseline",
            "team_a_xg_base": baseline["projected_home_xg"],
            "team_b_xg_base": baseline["projected_away_xg"],
            "team_a_xg_final": baseline["projected_home_xg"],
            "team_b_xg_final": baseline["projected_away_xg"],
            "projected_total": baseline["projected_total"],
            "most_likely_score": baseline["most_likely_score"],
            "team_a_win_prob": baseline["home_win_probability"],
            "draw_prob": baseline["draw_probability"],
            "team_b_win_prob": baseline["away_win_probability"],
            "confidence_score": baseline["confidence_score"],
            "confidence_label": baseline["confidence_label"],
            "risk_flags": "rating_only_baseline | no_current_style_inputs",
            "international_context_warnings": baseline["warnings"],
            "data_mode": "fallback_rating_only",
            "home_rating": baseline["home_rating"],
            "away_rating": baseline["away_rating"],
            "rating_diff": baseline["rating_diff"],
            "rating_status": baseline["rating_status"],
            "rating_warning": baseline["rating_warning"],
        }
        home_rating_source = home_rating.source_name if home_rating else ""
        away_rating_source = away_rating.source_name if away_rating else ""
        stat_source = str(matchup.get("stats_source_name", ""))
        row.update({
            "match_date": matchup["match_date"],
            "fixture_date": matchup.get("fixture_date", matchup["match_date"]),
            "kickoff_time": matchup.get("kickoff_time", ""),
            "kickoff_datetime_utc": matchup.get("kickoff_datetime_utc", ""),
            "competition": matchup["competition"],
            "round_name": matchup["round_name"],
            "group_name": matchup["group_name"],
            "current_fixture_data_mode": matchup["data_mode"],
            "data_support_level": support_label,
            "reliability_status": matchup["reliability_status"],
            "source_tier": matchup.get("source_tier", ""),
            "is_sample_data": matchup.get("is_sample_data", False),
            "source_fixture_name": matchup["source_fixture_name"],
            "fixture_source": matchup["source_fixture_name"],
            "rating_source_name": matchup["rating_source_name"],
            "rating_source_home": home_rating_source,
            "rating_source_away": away_rating_source,
            "stats_source_name": matchup["stats_source_name"],
            "stat_source_home": stat_source,
            "stat_source_away": stat_source,
            "scoreboard_source_name": matchup["scoreboard_source_name"],
            "fixture_source_status": matchup["source_fixture_status"],
            "current_source_warnings": matchup["warnings"],
            "stat_status": "basic_stats_available" if stat_source else "stats_missing",
            "data_coverage_score": matchup.get("data_coverage_score", 0),
            "missing_data_summary": matchup.get("missing_data_summary", ""),
            "source_audit_status": matchup.get("source_audit_status", slate_result["manifest"]["world_cup_readiness_status"]),
            "phase22_guardrails": "current_statsbomb_used=false | proxy_adjustments_enabled=false | no_betting_recommendations=true",
            "style_inputs_available": matchup.get("style_inputs_available", False),
            "style_inputs_warning": matchup.get("style_inputs_warning", "No current style-aware matchup inputs are available."),
            "rating_only_warning": baseline["warnings"],
            "primary_warning": (
                "Sample fixture data only. Do not treat this as a real current matchup."
                if _truthy(matchup.get("is_sample_data", False))
                else "Manual fixture is user supplied and not source-verified."
                if str(matchup.get("source_tier", "")) == "manual"
                else "Fixture + rating baseline only; no current style inputs."
            ),
            "source_warning": matchup["warnings"],
            "style_warning": matchup.get("style_inputs_warning", "No current style-aware matchup inputs are available."),
            "guardrail_flags": "current_statsbomb_used=false | proxy_adjustments_enabled=false | no_betting_recommendations=true",
            "fixture_resolution_status": matchup.get("fixture_resolution_status", ""),
            "is_resolved_fixture": matchup.get("is_resolved_fixture", True),
            "projection_eligible": matchup.get("projection_eligible", True),
            "projection_skip_reason": matchup.get("projection_skip_reason", ""),
            "fixture_temporal_status": matchup.get("fixture_temporal_status", ""),
            "is_current_slate": matchup.get("is_current_slate", False),
            "slate_window_status": matchup.get("slate_window_status", ""),
            "slate_skip_reason": matchup.get("slate_skip_reason", ""),
            "slate_window": matchup.get("slate_window", ""),
            "selected_by_slate_filter": matchup.get("selected_by_slate_filter", False),
            "fixture_key": matchup.get("fixture_key", ""),
            "deduplication_status": matchup.get("deduplication_status", ""),
            "primary_source": matchup.get("primary_source", matchup.get("source_fixture_name", "")),
            "duplicate_sources": matchup.get("duplicate_sources", ""),
            "source_priority_score": matchup.get("source_priority_score", 0),
        })
        rows.append(row)
    projections = pd.DataFrame(rows, columns=PROJECTION_COLUMNS)
    run_dir = slate_result["run_dir"]
    projection_path = run_dir / "current_international_projections.csv"
    projections.to_csv(projection_path, index=False)
    poisson_paths: dict[str, Any] = {}
    if build_poisson_board and not projections.empty:
        poisson_rows = projections.rename(columns={"team_a_xg_final": "projected_home_xg", "team_b_xg_final": "projected_away_xg"})
        poisson_paths = write_poisson_outputs(poisson_rows, run_dir / "poisson")
    report_path = _write_projection_report(run_dir / "current_international_projection_report.md", projections, full_slate)
    manifest = dict(slate_result["manifest"])
    manifest["projection_rows"] = len(projections)
    fallback_neutral_rows = int(((projections.get("rating_status", pd.Series(dtype=str)) == "both_ratings_missing") & (projections.get("team_a_xg_final", pd.Series(dtype=float)) == projections.get("team_b_xg_final", pd.Series(dtype=float)))).sum()) if not projections.empty else 0
    resolved_rows = int(full_slate.get("is_resolved_fixture", pd.Series(dtype=bool)).astype(bool).sum()) if not full_slate.empty else 0
    unresolved_rows = int((full_slate.get("fixture_resolution_status", pd.Series(dtype=str)).astype(str) == "unresolved_placeholder").sum()) if not full_slate.empty else 0
    skipped_placeholder_rows = unresolved_rows
    rating_coverage_resolved = (
        0.0
        if projections.empty
        else round(float((projections.get("rating_status", pd.Series(dtype=str)) == "both_ratings_available").mean()), 4)
    )
    strict_failure_reasons = []
    strict_warnings = []
    if strict_real_data:
        if len(slate) == 0:
            strict_failure_reasons.append("strict_real_data: no resolved projection-eligible fixtures available.")
        if not projections.empty and (projections.get("rating_status", pd.Series(dtype=str)) != "both_ratings_available").any():
            strict_failure_reasons.append("strict_real_data: ratings missing for one or more resolved projection-eligible teams.")
        if fallback_neutral_rows:
            strict_failure_reasons.append("strict_real_data: fallback-neutral rows remain among resolved projection-eligible fixtures.")
        if skipped_placeholder_rows:
            strict_warnings.append(PLACEHOLDER_SKIP_WARNING)
    manifest["strict_real_data"] = strict_real_data
    strict_status = "fail" if strict_failure_reasons else "warning" if strict_warnings else "pass"
    manifest["strict_real_data_status"] = strict_status
    manifest["strict_real_data_warnings"] = strict_warnings
    manifest["strict_failure_reasons"] = strict_failure_reasons
    manifest["resolved_rows"] = resolved_rows
    manifest["unresolved_rows"] = unresolved_rows
    manifest["projected_rows"] = len(projections)
    manifest["skipped_placeholder_rows"] = skipped_placeholder_rows
    manifest["rating_coverage_resolved"] = rating_coverage_resolved
    manifest["fallback_neutral_rows_resolved"] = fallback_neutral_rows
    manifest["include_unresolved_fixtures"] = include_unresolved_fixtures
    manifest["resolved_only"] = resolved_only
    manifest["slate_selection"] = slate_selection["summary"]
    manifest.update({
        "slate_window": slate_selection["summary"]["slate_window"],
        "effective_slate_window": slate_selection["summary"]["effective_slate_window"],
        "days_ahead": slate_selection["summary"]["days_ahead"],
        "date_from": slate_selection["summary"]["date_from"],
        "date_to": slate_selection["summary"]["date_to"],
        "include_past": slate_selection["summary"]["include_past"],
        "selected_fixture_count": slate_selection["summary"]["selected_fixtures"],
        "skipped_by_date_fixtures": slate_selection["summary"]["skipped_by_date_fixtures"],
        "skipped_past_fixtures": slate_selection["summary"]["skipped_past_fixtures"],
        "skipped_future_outside_window_fixtures": slate_selection["summary"]["skipped_future_outside_window_fixtures"],
        "skipped_unresolved_fixtures": slate_selection["summary"]["skipped_unresolved_fixtures"],
        "selected_date_range": slate_selection["summary"]["selected_date_range"],
        "earliest_selected_fixture_date": slate_selection["summary"]["earliest_selected_fixture_date"],
        "latest_selected_fixture_date": slate_selection["summary"]["latest_selected_fixture_date"],
        "max_matches_applied_after_slate_filter": True,
    })
    if slate_selection["summary"]["default_used_next_upcoming"]:
        manifest["warnings"] = list(dict.fromkeys([
            *manifest.get("warnings", []),
            "No fixtures were found on the as-of date; default slate selection used the next upcoming fixture date.",
        ]))
    if slate_selection["summary"]["effective_slate_window"] == "all_resolved":
        manifest["warnings"] = list(dict.fromkeys([
            *manifest.get("warnings", []),
            "All-resolved slate mode bypasses current-date filtering for review coverage.",
        ]))
    if skipped_placeholder_rows:
        manifest["warnings"] = list(dict.fromkeys([*manifest.get("warnings", []), PLACEHOLDER_SKIP_WARNING]))
    manifest["fallback_neutral_rows"] = fallback_neutral_rows
    manifest["output_paths"] = {
        **manifest["output_paths"],
        "projection_report": str(report_path),
        "projections": str(projection_path),
        **selection_paths,
        "poisson": poisson_paths,
    }
    manifest_path = _write_json(run_dir / "current_international_manifest.json", manifest)
    return {
        **slate_result,
        "slate": full_slate,
        "projections": projections,
        "selected_slate": slate,
        "slate_selection": slate_selection,
        "projections_path": projection_path,
        "projection_report_path": report_path,
        "poisson_paths": poisson_paths,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }
