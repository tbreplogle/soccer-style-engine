from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.projection_checkpoint import run_projection_checkpoint
from src.cli import build_parser
from src.international_current.current_international_slate import project_current_international
from src.international_current.current_international_schema import CurrentInternationalFixture
from src.international_current.fixture_resolution import classify_fixture, is_placeholder_team
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.static_viewer import build_static_viewer


pytestmark = pytest.mark.quick


def _write_cache(cache: Path, *, include_away_rating: bool = True, sample: bool = False) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    fixtures = [
        {
            "source_match_id": "resolved-1",
            "match_date": "2026-06-25",
            "competition": "FIFA World Cup",
            "round_name": "Group Stage",
            "group_name": "Group A",
            "home_team": "Mexico",
            "away_team": "South Africa",
            "neutral_site": "true",
            "status": "scheduled",
            "source_tier": "sample" if sample else "real",
            "reliability_status": "sample_only" if sample else "local_cache",
        },
        {
            "source_match_id": "placeholder-1",
            "match_date": "2026-07-01",
            "competition": "FIFA World Cup",
            "round_name": "Round of 32",
            "home_team": "W100",
            "away_team": "Runner-up Group A",
            "neutral_site": "true",
            "status": "scheduled",
            "source_tier": "sample" if sample else "real",
            "reliability_status": "sample_only" if sample else "local_cache",
        },
        {
            "source_match_id": "placeholder-2",
            "match_date": "2026-07-02",
            "competition": "FIFA World Cup",
            "round_name": "Round of 32",
            "home_team": "3A/B/C/D/F",
            "away_team": "Japan",
            "neutral_site": "true",
            "status": "scheduled",
            "source_tier": "sample" if sample else "real",
            "reliability_status": "sample_only" if sample else "local_cache",
        },
    ]
    with (cache / "fixtures.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fixtures[0].keys()))
        writer.writeheader()
        writer.writerows(fixtures)

    ratings = [
        {"team": "Mexico", "rating": "1912", "rating_date": "2026-06-25", "rating_source": "synthetic_real_rating"},
    ]
    if include_away_rating:
        ratings.append({"team": "South Africa", "rating": "1575", "rating_date": "2026-06-25", "rating_source": "synthetic_real_rating"})
    ratings.append({"team": "Japan", "rating": "1925", "rating_date": "2026-06-25", "rating_source": "synthetic_real_rating"})
    with (cache / "ratings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ratings[0].keys()))
        writer.writeheader()
        writer.writerows(ratings)


def test_placeholder_strings_are_detected_and_country_names_are_not():
    placeholders = ["TBD", "TBC", "Winner Match 100", "Runner-up Group A", "W100", "L101", "1F", "3A/B/C/D/F", ""]
    countries = ["Mexico", "South Africa", "United States", "Cote d'Ivoire", "Turkiye", "Curacao", "Netherlands"]

    assert all(is_placeholder_team(value) for value in placeholders)
    assert not any(is_placeholder_team(value) for value in countries)


def test_resolved_fixture_is_projection_eligible_and_placeholder_is_skipped():
    resolved = CurrentInternationalFixture(source_name="test", home_team="Mexico", away_team="South Africa")
    unresolved = CurrentInternationalFixture(source_name="test", home_team="W100", away_team="Runner-up Group A")

    resolved_status = classify_fixture(resolved)
    unresolved_status = classify_fixture(unresolved)

    assert resolved_status.fixture_resolution_status == "resolved"
    assert resolved_status.projection_eligible is True
    assert unresolved_status.fixture_resolution_status == "unresolved_placeholder"
    assert unresolved_status.projection_eligible is False
    assert "unresolved_placeholder" in unresolved_status.projection_skip_reason


def test_projection_skips_unresolved_by_default_and_strict_warns_not_fails(tmp_path):
    cache = tmp_path / "cache"
    output = tmp_path / "outputs" / "current_international"
    _write_cache(cache)

    result = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=cache,
        output_dir=output,
        strict_real_data=True,
        build_poisson_board=True,
        max_matches=10,
    )

    projections = result["projections"]
    manifest = result["manifest"]
    readiness_dir = output / "2026-06-25" / "fixture_readiness"

    assert len(projections) == 1
    assert projections.iloc[0]["team_a"] == "Mexico"
    assert set(projections["fixture_resolution_status"]) == {"resolved"}
    assert manifest["strict_real_data_status"] == "warning"
    assert manifest["strict_failure_reasons"] == []
    assert manifest["resolved_rows"] == 1
    assert manifest["unresolved_rows"] == 2
    assert manifest["skipped_placeholder_rows"] == 2
    assert manifest["rating_coverage_resolved"] == 1.0
    assert (readiness_dir / "fixture_readiness_summary.md").exists()
    assert len(pd.read_csv(readiness_dir / "unresolved_fixtures.csv")) == 2
    assert len(pd.read_csv(readiness_dir / "projection_skipped_fixtures.csv")) == 2
    assert (output / "2026-06-25" / "poisson" / "poisson_match_summary.csv").exists()
    poisson = pd.read_csv(output / "2026-06-25" / "poisson" / "poisson_match_summary.csv")
    assert len(poisson) == 1
    assert not poisson["home_team"].astype(str).str.contains("W100").any()


def test_include_unresolved_writes_reports_but_does_not_project_placeholders(tmp_path):
    cache = tmp_path / "cache"
    output = tmp_path / "outputs" / "current_international"
    _write_cache(cache)

    result = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=cache,
        output_dir=output,
        include_unresolved_fixtures=True,
        max_matches=10,
    )

    slate = result["slate"]
    assert len(slate) == 3
    assert len(result["projections"]) == 1
    assert "unresolved_placeholder" in set(slate["fixture_resolution_status"])
    skipped = pd.read_csv(output / "2026-06-25" / "fixture_readiness" / "projection_skipped_fixtures.csv")
    assert "W100" in set(skipped["home_team"])


def test_strict_fails_when_resolved_fixture_missing_rating(tmp_path):
    cache = tmp_path / "cache"
    output = tmp_path / "outputs" / "current_international"
    _write_cache(cache, include_away_rating=False)

    result = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=cache,
        output_dir=output,
        strict_real_data=True,
        max_matches=10,
    )

    assert result["manifest"]["strict_real_data_status"] == "fail"
    assert any("ratings missing" in reason for reason in result["manifest"]["strict_failure_reasons"])
    assert result["manifest"]["fallback_neutral_rows_resolved"] == 0


def test_projection_output_contains_resolution_fields_and_probabilities_vary(tmp_path):
    cache = tmp_path / "cache"
    output = tmp_path / "outputs" / "current_international"
    _write_cache(cache)

    result = project_current_international(as_of_date="2026-06-25", cache_dir=cache, output_dir=output)
    row = result["projections"].iloc[0]

    for column in ["fixture_resolution_status", "is_resolved_fixture", "projection_eligible", "projection_skip_reason"]:
        assert column in result["projections"].columns
    assert row["team_a_xg_final"] != row["team_b_xg_final"]
    assert row["team_a_win_prob"] != row["team_b_win_prob"]


def test_checkpoint_and_viewer_show_placeholder_skipped_warning(tmp_path):
    cache = tmp_path / "cache"
    outputs = tmp_path / "outputs"
    _write_cache(cache)

    checkpoint = run_projection_checkpoint(
        as_of_date="2026-06-25",
        run_current_international=True,
        cache_dir=cache,
        output_dir=outputs / "projection_checkpoints",
        build_poisson_board=True,
        max_matches=10,
    )
    viewer = build_static_viewer(outputs, outputs / "viewer")

    assert checkpoint["summary"]["status"] == "warning"
    assert "unresolved_placeholder_fixtures_skipped" in set(checkpoint["flags"]["flag_type"])
    assert checkpoint["poisson"] is not None
    detail = "\n".join(Path(path).read_text(encoding="utf-8") for path in viewer["run_pages"])
    assert "Unresolved placeholder fixtures were skipped and not projected." in detail
    assert "Unresolved Fixtures" in detail


def test_sample_data_still_requires_allow_sample_data(tmp_path):
    cache = tmp_path / "sample" / "cache"
    output = tmp_path / "outputs" / "current_international"
    _write_cache(cache, sample=True)

    rejected = project_current_international(as_of_date="2026-06-25", cache_dir=cache, output_dir=output / "rejected")
    allowed = project_current_international(as_of_date="2026-06-25", cache_dir=cache, output_dir=output / "allowed", allow_sample_data=True)

    assert rejected["projections"].empty
    assert rejected["manifest"]["projection_eligible_fixtures"] == 0
    assert len(allowed["projections"]) == 1
    assert bool(allowed["projections"].iloc[0]["is_sample_data"]) is True


def test_manual_fallback_still_projects_resolved_manual_rows(tmp_path):
    cache = tmp_path / "cache"
    output = tmp_path / "outputs" / "current_international"
    cache.mkdir(parents=True)
    (cache / "ratings.csv").write_text(
        "team,rating,rating_date,rating_source\nMexico,1912,2026-06-25,manual_test\nSouth Africa,1575,2026-06-25,manual_test\n",
        encoding="utf-8",
    )
    manual = tmp_path / "manual.csv"
    manual.write_text(
        "match_date,home_team,away_team,competition,neutral_site\n2026-06-25,Mexico,South Africa,FIFA World Cup,true\n",
        encoding="utf-8",
    )

    result = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=cache,
        output_dir=output,
        manual_matchups=manual,
        max_matches=10,
    )

    assert len(result["projections"]) == 1
    assert result["projections"].iloc[0]["fixture_resolution_status"] == "manual"
    assert result["projections"].iloc[0]["data_support_level"] == "low_manual_fixture_rating"


def test_guardrails_remain_registered():
    commands = build_parser()._subparsers._group_actions[0].choices
    assert "run-today" in commands
    assert "project-current-international" in commands
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
    payload = json.dumps({
        "current_statsbomb_used": False,
        "proxy_adjustments_enabled": False,
        "no_betting_recommendations": True,
    })
    assert "current_statsbomb_used" in payload
    assert "no_betting_recommendations" in payload
