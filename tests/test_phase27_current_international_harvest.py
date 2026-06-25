from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.cli import build_parser
from src.international_current.current_international_slate import project_current_international
from src.international_current.data_coverage import build_match_data_coverage
from src.international_current.fixture_harvest import harvest_current_international_fixtures
from src.international_current.rating_harvest import harvest_current_international_ratings
from src.international_current.stat_harvest import harvest_current_international_stats
from src.international_current.team_name_normalization import normalize_team_name
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.run_index import build_run_index
from src.viewer.static_viewer import build_static_viewer

pytestmark = pytest.mark.quick


def _write_cache(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "fixtures.csv").write_text(
        "\n".join([
            "match_date,kickoff_time,competition,round_name,group_name,home_team,away_team,neutral_site,venue,source_name,source_url",
            "2026-06-25,18:00,FIFA World Cup,Group Stage,Group E,USA,Ivory Coast,TRUE,Test Stadium,synthetic_cache,https://example.test/fixture",
            "2026-06-25,21:00,FIFA World Cup,Group Stage,Group F,Turkiye,South Korea,TRUE,Test Stadium,synthetic_cache,https://example.test/fixture2",
        ]),
        encoding="utf-8",
    )
    (cache / "ratings.csv").write_text(
        "\n".join([
            "team_name,rating,rating_source,rating_date",
            "United States,1840,synthetic_elo,2026-06-24",
            "Cote d'Ivoire,1760,synthetic_elo,2026-06-24",
            "Turkey,1710,synthetic_elo,2026-06-24",
            "Korea Republic,1690,synthetic_elo,2026-06-24",
        ]),
        encoding="utf-8",
    )
    (cache / "stats.csv").write_text(
        "\n".join([
            "team_name,goals_for_per_match,goals_against_per_match,xg_for_per_match,xg_against_per_match,shots_for_per_match,shots_against_per_match,source_name",
            "USA,1.8,0.9,,,12.0,8.0,synthetic_basic_stats",
            "Ivory Coast,1.5,1.1,,,10.0,9.0,synthetic_basic_stats",
        ]),
        encoding="utf-8",
    )


def test_fixture_rating_stat_harvest_from_synthetic_cache(tmp_path):
    cache = tmp_path / "cache"
    _write_cache(cache)

    fixtures = harvest_current_international_fixtures(as_of_date="2026-06-25", cache_dir=cache)
    assert len(fixtures["fixtures"]) == 2
    assert fixtures["fixtures_frame"]["source_tier"].eq("real").all()
    assert "United States" in set(fixtures["fixtures_frame"]["home_team"])
    assert "Cote d'Ivoire" in set(fixtures["fixtures_frame"]["away_team"])

    teams = sorted(set(fixtures["fixtures_frame"]["home_team"]).union(fixtures["fixtures_frame"]["away_team"]))
    ratings = harvest_current_international_ratings(fixture_teams=teams, cache_dir=cache)
    assert ratings["missing_rating_teams"] == []
    assert normalize_team_name("Korea Republic").normalized_name == "South Korea"
    assert normalize_team_name("Turkey").normalized_name == "Turkiye"

    stats = harvest_current_international_stats(fixture_teams=teams, cache_dir=cache)
    assert len(stats["stats_frame"]) == 2
    assert stats["stats_frame"]["xg_for_per_match"].isna().all()
    assert stats["stats_frame"]["shots_for_per_match"].notna().any()

    coverage = build_match_data_coverage(fixtures["fixtures_frame"], ratings["ratings_frame"], stats["stats_frame"])
    assert "real_fixture_basic_stats" in set(coverage["data_support_level"])
    assert coverage["xg_available"].eq(False).all()
    assert coverage["shots_available"].iloc[0] is True or bool(coverage["shots_available"].iloc[0]) is True


def test_project_current_international_uses_real_cache_and_writes_coverage(tmp_path):
    cache = tmp_path / "cache"
    output = tmp_path / "outputs" / "current_international"
    _write_cache(cache)

    result = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=cache,
        output_dir=output,
        max_matches=10,
        strict_real_data=True,
        build_poisson_board=True,
    )
    projections = result["projections"]
    assert len(projections) == 2
    assert result["manifest"]["real_fixture_count"] == 2
    assert result["manifest"]["manual_fixture_count"] == 0
    assert result["manifest"]["sample_fixture_count"] == 0
    assert result["manifest"]["strict_real_data_status"] == "pass"
    assert projections["data_support_level"].isin({"real_fixture_full_rating", "real_fixture_basic_stats"}).all()
    assert projections["fixture_source"].notna().all()
    assert projections["rating_source_home"].notna().all()
    assert projections["missing_data_summary"].str.contains("xg").any()
    assert (output / "2026-06-25" / "source_audit" / "match_data_coverage.csv").exists()
    assert (output / "2026-06-25" / "poisson" / "poisson_match_summary.csv").exists()

    viewer = build_static_viewer(tmp_path / "outputs", tmp_path / "viewer")
    assert viewer["runs_included"] == 1
    detail = (tmp_path / "viewer" / "runs" / "current_international_2026-06-25.html").read_text(encoding="utf-8")
    assert "Source Audit" in detail
    assert "Match Data Coverage" in detail


def test_strict_real_data_warns_when_no_real_cache(tmp_path):
    result = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=tmp_path / "empty_cache",
        output_dir=tmp_path / "outputs",
        strict_real_data=True,
    )
    assert result["manifest"]["strict_real_data_status"] == "fail"
    assert result["manifest"]["real_fixture_count"] == 0
    assert result["projections"].empty


def test_sample_fixture_cache_rejected_by_default(tmp_path):
    sample_cache = tmp_path / "data" / "sample" / "current_international"
    sample_cache.mkdir(parents=True)
    (sample_cache / "fixtures.csv").write_text(
        "match_date,competition,home_team,away_team\n2026-06-25,FIFA World Cup,USA,Japan\n",
        encoding="utf-8",
    )
    result = harvest_current_international_fixtures(as_of_date="2026-06-25", cache_dir=sample_cache)
    assert result["fixtures_frame"].empty
    assert result["audit_frame"]["recommendation"].str.contains("Sample fixture cache rejected").any()


def test_phase27_cli_and_guardrails_registered():
    commands = build_parser()._subparsers._group_actions[0].choices
    assert "audit-current-international-sources" in commands
    assert "project-current-international" in commands
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
