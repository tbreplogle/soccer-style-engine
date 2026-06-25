from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import src.cli as cli
from src.data_sources.coverage_matrix import build_coverage_matrix, recommend_source_stack
from src.data_sources.source_registry import get_source_registry
from src.data_sources.source_result import SourceResult
from src.operational.defaults import OPERATIONAL_DEFAULTS


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.quick


def test_source_registry_contains_required_sources():
    registry = get_source_registry()
    for source in [
        "football_data",
        "soccerdata",
        "sofascore",
        "whoscored",
        "fbref",
        "understat",
        "clubelo",
        "eloratings",
        "statsbomb_open_data",
    ]:
        assert source in registry
        assert registry[source]["is_free"] is True


def test_registry_metadata_key_truths():
    registry = get_source_registry()
    assert registry["statsbomb_open_data"]["historical_only"] is True
    assert registry["football_data"]["current_data_expected"] is True
    assert registry["football_data"]["club_coverage"] is True
    assert registry["sofascore"]["world_cup_coverage"] is True
    assert registry["sofascore"]["current_data_expected"] is True
    assert registry["whoscored"]["event_data_possible"] is True
    assert registry["understat"]["world_cup_coverage"] is False
    assert registry["clubelo"]["strength_rating_possible"] is True
    assert registry["clubelo"]["club_coverage"] is True
    assert registry["eloratings"]["strength_rating_possible"] is True
    assert registry["eloratings"]["international_coverage"] is True


def test_source_result_schema_validation():
    result = SourceResult(
        source_name="football_data",
        status="success",
        rows_returned=3,
        fields_available=["Date", "HomeTeam"],
        data_mode="current_results_stats",
    )
    assert result.to_dict()["source_name"] == "football_data"
    with pytest.raises(ValueError):
        SourceResult(source_name="bad", status="unknown")
    with pytest.raises(ValueError):
        SourceResult(source_name="bad", data_mode="current_magic")


def test_coverage_matrix_builds():
    frame = build_coverage_matrix([
        SourceResult(source_name="football_data", status="success", currentness_status="available_local", reliability_status="local_csv_available").to_dict()
    ])
    assert {"source", "club_current", "world_cup_current", "xg", "ratings", "current_status"}.issubset(frame.columns)
    football = frame[frame["source"].eq("football_data")].iloc[0]
    assert bool(football["club_current"]) is True


def test_source_recommendations():
    assert recommend_source_stack("club_projection")[:2] == ["football_data", "clubelo"]
    assert recommend_source_stack("world_cup_projection")[:2] == ["sofascore", "eloratings"]
    assert recommend_source_stack("style_event_proxy")[:2] == ["whoscored", "sofascore"]
    with pytest.raises(ValueError):
        recommend_source_stack("unsupported")


def test_audit_free_sources_command_exists_and_no_network_mode_works(tmp_path):
    parser = cli.build_parser()
    assert "audit-free-sources" in parser._subparsers._group_actions[0].choices
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "E0_2526.csv").write_text(
        "Date,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,HST,AST,HC,AC,B365H\n01/05/26,A,B,1,0,10,8,4,3,5,4,2.0\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "audit-free-sources",
            "--as-of-date",
            "2026-05-25",
            "--output-dir",
            str(tmp_path / "audits"),
            "--football-data-raw-dir",
            str(raw),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Sources audited: 9" in result.stdout
    assert (tmp_path / "audits" / "2026-05-25_local" / "source_audit_summary.md").exists()
    assert (tmp_path / "audits" / "2026-05-25_local" / "source_audit_results.csv").exists()
    assert (tmp_path / "audits" / "2026-05-25_local" / "source_audit_manifest.json").exists()


def test_generated_audit_outputs_are_ignored():
    for path in [
        "outputs/source_audits/2026-05-25/source_audit_summary.md",
        "data/source_cache/example.json",
        "data/raw/scraped/example.json",
    ]:
        result = subprocess.run(["git", "check-ignore", path], cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, path


def test_guardrails_v1_and_run_today_still_exist():
    parser = cli.build_parser()
    commands = parser._subparsers._group_actions[0].choices
    assert "validate-v1" in commands
    assert "run-today" in commands
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
    source_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in [
        "src/data_sources/source_registry.py",
        "src/data_sources/source_audit.py",
        "docs/FREE_CURRENT_DATA_ROADMAP.md",
        "docs/SOURCE_ADAPTERS.md",
    ])
    assert "current StatsBomb" in source_text
    assert "best bet" not in source_text.lower()
    assert "betting pick" not in source_text.lower()
