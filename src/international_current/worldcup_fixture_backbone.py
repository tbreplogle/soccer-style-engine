from __future__ import annotations

import csv
import json
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_sources.adapters.eloratings_adapter import audit_eloratings_current
from src.data_sources.adapters.openfootball_worldcup_adapter import audit_openfootball_worldcup, parse_openfootball_fixtures
from src.international_current.current_international_schema import CurrentInternationalFixture, CurrentInternationalTeamRating
from src.international_current.team_name_normalization import normalize_team_pair


DEFAULT_FIXTURE_SAMPLE = Path("data/sample/worldcup_static_fixtures_openfootball_sample.json")
DEFAULT_RATING_SAMPLE = Path("data/sample/eloratings_sample.csv")


def _fixture_key(fixture: CurrentInternationalFixture) -> tuple[str, str, str, str]:
    return (
        fixture.match_date,
        fixture.competition.strip().lower(),
        fixture.home_team.strip().lower(),
        fixture.away_team.strip().lower(),
    )


def dedupe_fixtures(fixtures: list[CurrentInternationalFixture]) -> list[CurrentInternationalFixture]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[CurrentInternationalFixture] = []
    for fixture in fixtures:
        key = _fixture_key(fixture)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fixture)
    return deduped


def load_manual_fixture_csv(path: str | Path) -> list[CurrentInternationalFixture]:
    fixtures: list[CurrentInternationalFixture] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            home, away, warnings = normalize_team_pair(row.get("home_team") or row.get("team_a") or "", row.get("away_team") or row.get("team_b") or "")
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
                warnings=[
                    "Manual fixture fallback; verify teams, venue, neutral-site status, and kickoff externally.",
                    *(warnings or []),
                    row.get("notes") or "No current stats/xG/style inputs attached.",
                ],
            ))
    return fixtures


def load_static_worldcup_fixtures(
    path: str | Path = DEFAULT_FIXTURE_SAMPLE,
    *,
    competition: str = "FIFA World Cup",
) -> list[CurrentInternationalFixture]:
    fixtures = parse_openfootball_fixtures(path)
    if competition:
        fixtures = [fixture for fixture in fixtures if not fixture.competition or competition.lower() in fixture.competition.lower()]
    normalized = []
    for fixture in fixtures:
        home, away, warnings = normalize_team_pair(fixture.home_team, fixture.away_team)
        normalized.append(CurrentInternationalFixture(
            **{
                **fixture.to_dict(),
                "home_team": home,
                "away_team": away,
                "warnings": list(dict.fromkeys([
                    *fixture.warnings,
                    *warnings,
                    "Static fixture backbone only; no current event data, xG, lineups, injuries, or style inputs.",
                ])),
            }
        ))
    return dedupe_fixtures(normalized)


def fixture_data_mode(fixture: CurrentInternationalFixture) -> str:
    if fixture.source_name == "manual_current_fixture" or fixture.reliability_status == "manual_fallback":
        return "manual_current_fixture"
    if fixture.home_score is not None or fixture.away_score is not None:
        return "current_fixture_result"
    return "current_fixture_only"


def _fixture_frame(fixtures: list[CurrentInternationalFixture]) -> pd.DataFrame:
    columns = [item.name for item in fields(CurrentInternationalFixture)]
    frame = pd.DataFrame([fixture.to_dict() for fixture in fixtures], columns=columns)
    if not frame.empty:
        frame["data_mode"] = [fixture_data_mode(fixture) for fixture in fixtures]
        frame["style_inputs_available"] = False
        frame["style_inputs_warning"] = "No current style-aware matchup inputs are available from static fixtures."
    return frame


def _rating_frame(ratings: list[CurrentInternationalTeamRating]) -> pd.DataFrame:
    columns = [item.name for item in fields(CurrentInternationalTeamRating)]
    return pd.DataFrame([rating.to_dict() for rating in ratings], columns=columns)


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


def _write_summary(path: Path, manifest: dict[str, Any], fixtures: pd.DataFrame, ratings: pd.DataFrame) -> Path:
    lines = [
        "# World Cup Fixture + Elo Backbone",
        "",
        f"Generated at: {manifest['generated_at']}",
        f"As-of date: `{manifest['as_of_date']}`",
        f"Readiness: `{manifest['readiness_status']}`",
        "",
        "## Guardrails",
        "",
        "- This is a fixture + rating backbone for baseline score projections.",
        "- It is not style-aware projection yet.",
        "- Static fixtures and Elo ratings are not event, tracking, xG, lineup, injury, or style data.",
        "- No current StatsBomb data is used.",
        "- No betting recommendations are produced.",
        "",
        "## Counts",
        "",
        f"- Fixtures: {manifest['fixture_count']}",
        f"- Ratings: {manifest['rating_count']}",
        f"- Teams missing ratings: {manifest['teams_missing_ratings_count']}",
        "",
        "## Fixtures",
        "",
    ]
    fixture_cols = [col for col in ["match_date", "home_team", "away_team", "competition", "data_mode"] if col in fixtures.columns]
    lines.extend(_markdown_table(fixtures[fixture_cols] if not fixtures.empty else fixtures))
    lines.extend(["", "## Ratings", ""])
    rating_cols = [col for col in ["team", "rating_value", "rating_type", "rating_date", "rank", "source_name"] if col in ratings.columns]
    lines.extend(_markdown_table(ratings[rating_cols] if not ratings.empty else ratings))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_worldcup_backbone(
    *,
    as_of_date: str,
    competition: str = "FIFA World Cup",
    allow_network: bool = False,
    fixture_source: str | Path = DEFAULT_FIXTURE_SAMPLE,
    ratings_source: str | Path = DEFAULT_RATING_SAMPLE,
    output_dir: str | Path = "outputs/current_international",
) -> dict[str, Any]:
    fixture_result, fixtures = audit_openfootball_worldcup(
        cache_path=fixture_source,
        allow_network=allow_network,
        use_sample_fallback=True,
    )
    rating_result, ratings = audit_eloratings_current(
        cache_path=ratings_source,
        allow_network=allow_network,
        use_sample_fallback=True,
    )
    fixtures = dedupe_fixtures(fixtures)
    rating_names = {rating.team for rating in ratings if rating.team and rating.rating_value is not None}
    fixture_teams = sorted({team for fixture in fixtures for team in [fixture.home_team, fixture.away_team] if team})
    missing = [team for team in fixture_teams if team not in rating_names]
    if fixtures and ratings and not missing:
        readiness = "ready_fixture_and_rating"
    elif fixtures:
        readiness = "ready_fixture_only"
    else:
        readiness = "insufficient"
    run_dir = Path(output_dir) / as_of_date / "worldcup_backbone"
    run_dir.mkdir(parents=True, exist_ok=True)
    fixture_frame = _fixture_frame(fixtures)
    rating_frame = _rating_frame(ratings)
    fixture_path = run_dir / "worldcup_fixture_backbone.csv"
    rating_path = run_dir / "worldcup_rating_backbone.csv"
    fixture_frame.to_csv(fixture_path, index=False)
    rating_frame.to_csv(rating_path, index=False)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of_date,
        "competition": competition,
        "allow_network": allow_network,
        "fixture_source": str(fixture_source),
        "ratings_source": str(ratings_source),
        "fixture_count": len(fixtures),
        "rating_count": len(ratings),
        "teams_missing_ratings": missing,
        "teams_missing_ratings_count": len(missing),
        "readiness_status": readiness,
        "style_inputs_available": False,
        "style_inputs_warning": "No current event/xG/tracking/style-aware matchup inputs are available in the fixture + rating backbone.",
        "source_results": {
            "openfootball_worldcup": fixture_result.to_dict(),
            "eloratings": rating_result.to_dict(),
        },
        "guardrails": {
            "current_statsbomb_used": False,
            "the_stats_api_used": False,
            "betting_recommendations": False,
            "rating_only_not_style_aware": True,
        },
        "output_paths": {
            "fixtures": str(fixture_path),
            "ratings": str(rating_path),
            "summary": str(run_dir / "worldcup_backbone_summary.md"),
            "manifest": str(run_dir / "worldcup_backbone_manifest.json"),
        },
    }
    manifest_path = run_dir / "worldcup_backbone_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    summary_path = _write_summary(run_dir / "worldcup_backbone_summary.md", manifest, fixture_frame, rating_frame)
    return {
        "run_dir": run_dir,
        "fixtures": fixtures,
        "ratings": ratings,
        "fixture_frame": fixture_frame,
        "rating_frame": rating_frame,
        "fixture_path": fixture_path,
        "rating_path": rating_path,
        "summary_path": summary_path,
        "manifest_path": manifest_path,
        "manifest": manifest,
        "fixture_result": fixture_result,
        "rating_result": rating_result,
    }

