from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import src.cli as cli
from src.data_sources.adapters.eloratings_adapter import audit_eloratings_current, parse_eloratings
from src.data_sources.adapters.openfootball_worldcup_adapter import audit_openfootball_worldcup, parse_openfootball_fixtures
from src.data_sources.coverage_matrix import recommend_source_stack
from src.international_current.rating_projection import RATING_ONLY_WARNING, build_rating_lookup, project_from_fixture_and_ratings
from src.international_current.team_name_normalization import normalize_team_name
from src.international_current.worldcup_fixture_backbone import build_worldcup_backbone, dedupe_fixtures
from src.operational.defaults import OPERATIONAL_DEFAULTS


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.quick


def test_openfootball_sample_fixture_parser_and_dedupe():
    sample = ROOT / "data" / "sample" / "worldcup_static_fixtures_openfootball_sample.json"
    fixtures = parse_openfootball_fixtures(sample)
    assert len(fixtures) == 3
    assert fixtures[0].home_team == "United States"
    assert fixtures[0].away_team == "Canada"
    assert "Fixture-only row" in " ".join(fixtures[0].warnings)
    assert len(dedupe_fixtures([fixtures[0], fixtures[0], fixtures[1]])) == 2


def test_eloratings_sample_parser_and_lookup():
    sample = ROOT / "data" / "sample" / "eloratings_sample.csv"
    ratings = parse_eloratings(sample)
    lookup = build_rating_lookup(ratings)
    assert lookup["United States"].rating_value == 1810
    assert lookup["South Korea"].team == "South Korea"
    assert lookup["Cote d'Ivoire"].rating_type == "elo"


def test_team_name_normalization_common_aliases():
    assert normalize_team_name("USA").normalized_name == "United States"
    assert normalize_team_name("Korea Republic").normalized_name == "South Korea"
    assert normalize_team_name("Ivory Coast").normalized_name == "Cote d'Ivoire"
    assert normalize_team_name("DR Congo").normalized_name == "Congo DR"
    assert normalize_team_name("Curaçao").normalized_name == "Curacao"
    assert normalize_team_name("Czechia").normalized_name == "Czech Republic"
    assert normalize_team_name("Bosnia-Herzegovina").normalized_name == "Bosnia and Herzegovina"
    unknown = normalize_team_name("Made Up FC", known_names=["United States"])
    assert unknown.normalized_name == "Made Up FC"
    assert "Unknown" in unknown.warning


def test_rating_projection_baseline_warning_and_confidence_cap():
    fixtures = parse_openfootball_fixtures(ROOT / "data" / "sample" / "worldcup_static_fixtures_openfootball_sample.json")
    ratings = build_rating_lookup(parse_eloratings(ROOT / "data" / "sample" / "eloratings_sample.csv"))
    row = project_from_fixture_and_ratings(fixtures[0], ratings["United States"], ratings["Canada"])
    assert row["data_support_level"] == "medium_current_fixture_rating"
    assert row["confidence_label"] != "High"
    assert row["confidence_score"] < 60
    assert RATING_ONLY_WARNING in row["warnings"]
    assert "style-aware matchup inputs" in row["warnings"]
    assert "bet" not in row["warnings"].lower()


def test_missing_rating_lowers_support_and_warns():
    fixture = parse_openfootball_fixtures(ROOT / "data" / "sample" / "worldcup_static_fixtures_openfootball_sample.json")[0]
    row = project_from_fixture_and_ratings(fixture, None, None)
    assert row["data_support_level"] == "low_fixture_only"
    assert "Missing rating" in row["warnings"]
    assert row["confidence_label"] == "Low"


def test_worldcup_backbone_no_network_uses_samples(tmp_path):
    result = build_worldcup_backbone(
        as_of_date="2026-06-24",
        allow_network=False,
        output_dir=tmp_path,
    )
    assert result["manifest"]["readiness_status"] == "ready_fixture_and_rating"
    assert result["manifest"]["fixture_count"] == 3
    assert result["manifest"]["rating_count"] >= 6
    assert result["manifest"]["style_inputs_available"] is False
    assert result["fixture_path"].exists()
    assert result["rating_path"].exists()
    assert result["summary_path"].exists()


def test_build_worldcup_backbone_cli_exists_and_runs(tmp_path):
    parser = cli.build_parser()
    assert "build-worldcup-backbone" in parser._subparsers._group_actions[0].choices
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "build-worldcup-backbone",
            "--as-of-date",
            "2026-06-24",
            "--no-network",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Readiness: ready_fixture_and_rating" in result.stdout


def test_current_audit_and_projection_use_backbone(tmp_path):
    audit = subprocess.run(
        [sys.executable, "-m", "src.cli", "audit-current-international", "--as-of-date", "2026-06-24", "--output-dir", str(tmp_path / "audit")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Fixtures found: 3" in audit.stdout
    assert "Ratings found:" in audit.stdout
    projection = subprocess.run(
        [sys.executable, "-m", "src.cli", "project-current-international", "--as-of-date", "2026-06-24", "--no-network", "--max-matches", "10", "--output-dir", str(tmp_path / "proj")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Projection rows: 3" in projection.stdout
    report = tmp_path / "proj" / "2026-06-24" / "current_international_projection_report.md"
    assert report.exists()
    assert "Low" in report.read_text(encoding="utf-8") or "Medium-Low" in report.read_text(encoding="utf-8")


def test_manual_fallback_projection_still_works(tmp_path):
    manual = ROOT / "data" / "sample" / "current_international_matchups.csv"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "project-current-international",
            "--manual-matchups",
            str(manual),
            "--as-of-date",
            "2026-06-24",
            "--no-network",
            "--max-matches",
            "10",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Projection rows:" in result.stdout


def test_phase24_source_policy_and_guardrails():
    stack = recommend_source_stack("world_cup_projection")
    assert "thestatsapi_worldcup" not in stack
    assert stack[:2] == ["openfootball_worldcup", "eloratings"]
    source_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in [
        "src/international_current/current_international_slate.py",
        "src/international_current/worldcup_fixture_backbone.py",
        "docs/PROJECTION_STYLE_ALIGNMENT.md",
        "docs/WORLDCUP_FIXTURE_ELO_BACKBONE.md",
    ])
    assert "current_statsbomb_used" in source_text
    assert "style-aware" in source_text
    assert "score projection" in source_text.lower() or "score projections" in source_text.lower()
    assert "betting recommendation" in source_text
    assert "best bet" not in source_text.lower()
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False


def test_phase24_docs_and_ignored_outputs():
    alignment = ROOT / "docs" / "PROJECTION_STYLE_ALIGNMENT.md"
    text = alignment.read_text(encoding="utf-8")
    assert "score projections" in text
    assert "matchup style" in text
    assert "style-aware matchup inputs" in text
    ignored = subprocess.run(
        ["git", "check-ignore", "outputs/current_international/2026-06-24/worldcup_backbone/worldcup_backbone_manifest.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0
    cache_ignored = subprocess.run(["git", "check-ignore", "data/source_cache/openfootball/example.json"], cwd=ROOT, capture_output=True, text=True)
    assert cache_ignored.returncode == 0


def test_adapters_no_network_sample_fallback_and_sofascore_unavailable():
    fixture_result, fixtures = audit_openfootball_worldcup(allow_network=False, use_sample_fallback=True)
    rating_result, ratings = audit_eloratings_current(allow_network=False, use_sample_fallback=True)
    assert fixture_result.status == "success"
    assert len(fixtures) == 3
    assert rating_result.status == "success"
    assert ratings

