from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_sources.adapters.eloratings_adapter import audit_eloratings_current
from src.data_sources.adapters.espn_scoreboard_adapter import audit_espn_scoreboard
from src.data_sources.adapters.fbref_adapter import audit_fbref_international
from src.data_sources.adapters.openfootball_worldcup_adapter import NO_REAL_FIXTURE_WARNING, audit_openfootball_worldcup
from src.data_sources.adapters.sofascore_adapter import audit_sofascore_current_international
from src.data_sources.source_result import SourceResult
from src.international_current.current_international_schema import (
    CurrentInternationalFixture,
    CurrentInternationalMatchStats,
    CurrentInternationalSlateRow,
    CurrentInternationalSourceSummary,
    CurrentInternationalTeamRating,
)
from src.international_current.rating_projection import project_from_fixture_and_ratings
from src.international_current.team_name_normalization import normalize_team_pair
from src.models.international_projection import project_international_match


SLATE_COLUMNS = [
    "match_date",
    "competition",
    "round_name",
    "group_name",
    "home_team",
    "away_team",
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
    "rating_source_name",
    "stats_source_name",
    "scoreboard_source_name",
    "current_source_warnings",
    "phase22_guardrails",
    "style_inputs_available",
    "style_inputs_warning",
    "rating_only_warning",
    "primary_warning",
    "source_warning",
    "style_warning",
    "guardrail_flags",
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
    if fixture and rating:
        if fixture.source_name == "espn_scoreboard":
            return "medium_current_fixture_scoreboard_rating"
        if fixture.source_name == "manual_current_fixture" or fixture.reliability_status == "manual_fallback":
            return "low_manual_fixture_rating"
        return "medium_current_fixture_rating"
    if fixture:
        if fixture.source_name == "manual_current_fixture" or fixture.reliability_status == "manual_fallback":
            return "low_manual_fixture_rating"
        return "low_fixture_only"
    if rating:
        return "historical_context_only"
    return "insufficient"


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
    return CurrentInternationalSlateRow(
        match_date=fixture.match_date,
        competition=fixture.competition,
        round_name=fixture.round_name,
        group_name=fixture.group_name,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
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
) -> dict[str, Any]:
    openfootball_result, openfootball_fixtures = audit_openfootball_worldcup(
        allow_network=allow_network,
        use_sample_fallback=allow_sample_data,
    )
    # Phase 24 does not depend on SofaScore after the safe probe returned HTTP 403.
    # Use cache/local mode only here; do not force live SofaScore access in the default workflow.
    sofascore_result, sofascore_fixtures, sofascore_stats = audit_sofascore_current_international(
        allow_network=False,
        as_of_date=as_of_date,
        competition=competition,
    )
    if allow_network:
        sofascore_result.warnings.append("SofaScore live probing is intentionally not forced in the Phase 24 default backbone after safe requests returned HTTP 403.")
    eloratings_result, ratings = audit_eloratings_current(
        allow_network=allow_network,
        use_sample_fallback=allow_sample_data or bool(manual_matchups),
    )
    espn_result, espn_fixtures = audit_espn_scoreboard(allow_network=allow_network)
    fbref_result = audit_fbref_international(allow_network=allow_network)
    manual_fixtures = parse_manual_current_matchups(manual_matchups) if manual_matchups else []
    fixtures = [*openfootball_fixtures, *sofascore_fixtures, *espn_fixtures, *manual_fixtures]
    if competition:
        fixtures = [fixture for fixture in fixtures if not fixture.competition or competition.lower() in fixture.competition.lower()]
    results = [openfootball_result, eloratings_result, sofascore_result, espn_result, fbref_result]
    summaries = _source_summary(results, len(manual_fixtures))
    rating_names = {rating.team for rating in ratings if rating.team and rating.rating_value is not None}
    fixture_teams = sorted({team for fixture in fixtures for team in [fixture.home_team, fixture.away_team] if team})
    missing_ratings = [team for team in fixture_teams if team not in rating_names]
    if openfootball_fixtures and ratings and not missing_ratings:
        readiness = "ready_fixture_and_rating"
    elif fixtures and fixtures == manual_fixtures:
        readiness = "manual_only"
    elif fixtures:
        readiness = "ready_fixture_only"
    else:
        readiness = "insufficient"
    run_dir = _run_dir(output_dir, as_of_date)
    summary_path = _write_source_summary(run_dir / "current_international_source_summary.md", results, summaries, allow_network)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of_date or date.today().isoformat(),
        "competition": competition,
        "allow_network": allow_network,
        "allow_sample_data": allow_sample_data,
        "fixture_count": len(fixtures),
        "real_fixture_count": len([fixture for fixture in fixtures if not fixture.is_sample_data and fixture.source_tier != "manual"]),
        "manual_fixture_count": len([fixture for fixture in fixtures if fixture.source_tier == "manual" or fixture.reliability_status == "manual_fallback"]),
        "sample_fixture_count": len([fixture for fixture in fixtures if fixture.is_sample_data or fixture.source_tier == "sample"]),
        "rating_count": len(ratings),
        "teams_missing_ratings": missing_ratings,
        "teams_missing_ratings_count": len(missing_ratings),
        "world_cup_readiness_status": readiness,
        "style_inputs_available": False,
        "style_inputs_warning": "No current event/xG/tracking/style-aware matchup inputs are available; do not report style-aware projection ready.",
        "stats_count": len(sofascore_stats),
        "sofascore": {
            "fixture_count": len(sofascore_fixtures),
            "match_stats_count": len(sofascore_stats),
            "xg_found": any(stat.xg_home is not None or stat.xg_away is not None for stat in sofascore_stats),
            "xgot_found": any(stat.xgot_home is not None or stat.xgot_away is not None for stat in sofascore_stats),
            "lineups_found": any(stat.lineups_available for stat in sofascore_stats),
            "player_ratings_found": any(stat.player_ratings_available for stat in sofascore_stats),
        },
        "source_status_counts": _result_frame(results)["status"].value_counts().to_dict(),
        "guardrails": {
            "current_statsbomb_used": False,
            "the_stats_api_used": False,
            "fixture_only_not_true_style": True,
            "proxy_adjustments_enabled": False,
            "betting_recommendations": False,
        },
        "output_paths": {"source_summary": str(summary_path)},
        "warnings": [] if fixtures else [NO_REAL_FIXTURE_WARNING],
    }
    manifest_path = _write_json(run_dir / "current_international_manifest.json", manifest)
    return {
        "run_dir": run_dir,
        "results": results,
        "source_summaries": summaries,
        "fixtures": fixtures,
        "ratings": ratings,
        "stats": sofascore_stats,
        "source_summary_path": summary_path,
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
) -> dict[str, Any]:
    audit = audit_current_international_sources(
        as_of_date=as_of_date,
        competition=competition,
        manual_matchups=manual_matchups,
        allow_network=allow_network,
        allow_sample_data=allow_sample_data,
        output_dir=output_dir,
    )
    ratings = _rating_lookup(audit["ratings"])
    stats_lookup = {stat.source_match_id: stat for stat in audit["stats"] if stat.source_match_id}
    rows = [_fixture_to_slate_row(fixture, ratings, stats_lookup).to_dict() for fixture in audit["fixtures"]]
    frame = pd.DataFrame(rows)
    for column in SLATE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[SLATE_COLUMNS]
    run_dir = audit["run_dir"]
    slate_path = run_dir / "current_international_slate.csv"
    slate_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(slate_path, index=False)
    manifest = dict(audit["manifest"])
    manifest["slate_rows"] = len(frame)
    manifest["output_paths"] = {
        **manifest["output_paths"],
        "slate": str(slate_path),
        "manifest": str(run_dir / "current_international_manifest.json"),
    }
    manifest_path = _write_json(run_dir / "current_international_manifest.json", manifest)
    return {**audit, "slate": frame, "slate_path": slate_path, "manifest_path": manifest_path, "manifest": manifest}


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
    ]
    lines.extend(_markdown_table(projections[summary_cols] if not projections.empty else projections))
    lines.extend(["", "## Current Slate Inputs", ""])
    slate_cols = ["match_date", "home_team", "away_team", "source_fixture_name", "data_mode", "data_support_level", "warnings"]
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
) -> dict[str, Any]:
    slate_result = build_current_international_slate(
        as_of_date=as_of_date,
        competition=competition,
        manual_matchups=manual_matchups,
        allow_network=allow_network,
        allow_sample_data=allow_sample_data,
        output_dir=output_dir,
    )
    slate = slate_result["slate"].head(max_matches).copy()
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
        row.update({
            "match_date": matchup["match_date"],
            "competition": matchup["competition"],
            "round_name": matchup["round_name"],
            "group_name": matchup["group_name"],
            "current_fixture_data_mode": matchup["data_mode"],
            "data_support_level": matchup["data_support_level"],
            "reliability_status": matchup["reliability_status"],
            "source_tier": matchup.get("source_tier", ""),
            "is_sample_data": matchup.get("is_sample_data", False),
            "source_fixture_name": matchup["source_fixture_name"],
            "rating_source_name": matchup["rating_source_name"],
            "stats_source_name": matchup["stats_source_name"],
            "scoreboard_source_name": matchup["scoreboard_source_name"],
            "current_source_warnings": matchup["warnings"],
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
        })
        rows.append(row)
    projections = pd.DataFrame(rows, columns=PROJECTION_COLUMNS)
    run_dir = slate_result["run_dir"]
    projection_path = run_dir / "current_international_projections.csv"
    projections.to_csv(projection_path, index=False)
    report_path = _write_projection_report(run_dir / "current_international_projection_report.md", projections, slate_result["slate"])
    manifest = dict(slate_result["manifest"])
    manifest["projection_rows"] = len(projections)
    manifest["output_paths"] = {
        **manifest["output_paths"],
        "projection_report": str(report_path),
        "projections": str(projection_path),
    }
    manifest_path = _write_json(run_dir / "current_international_manifest.json", manifest)
    return {
        **slate_result,
        "projections": projections,
        "projections_path": projection_path,
        "projection_report_path": report_path,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }
