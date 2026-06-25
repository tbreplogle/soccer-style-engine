from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import src.cli as cli
from src.data_sources.adapters.eloratings_adapter import audit_eloratings_current
from src.data_sources.adapters.espn_scoreboard_adapter import audit_espn_scoreboard
from src.data_sources.adapters.fbref_adapter import audit_fbref_international
from src.data_sources.adapters.openfootball_worldcup_adapter import audit_openfootball_worldcup
from src.data_sources.adapters.sofascore_adapter import audit_sofascore_current_international
from src.data_sources.adapters.thestatsapi_worldcup_adapter import audit_thestatsapi_worldcup
from src.data_sources.coverage_matrix import recommend_source_stack
from src.data_sources.source_registry import get_source_registry
from src.international_current.current_international_schema import CurrentInternationalFixture
from src.international_current.current_international_slate import (
    build_current_international_slate,
    determine_data_support_level,
    parse_manual_current_matchups,
    project_current_international,
)
from src.operational.defaults import OPERATIONAL_DEFAULTS


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.quick


def test_phase22_registry_and_source_priority():
    registry = get_source_registry()
    for source in ["openfootball_worldcup", "thestatsapi_worldcup", "espn_scoreboard"]:
        assert source in registry
        assert registry[source]["current_data_expected"] is True
        assert registry[source]["world_cup_coverage"] is True
    assert registry["statsbomb_open_data"]["historical_only"] is True
    assert recommend_source_stack("world_cup_projection")[:3] == [
        "openfootball_worldcup",
        "thestatsapi_worldcup",
        "sofascore",
    ]


def test_phase22_schema_and_support_labels():
    fixture = CurrentInternationalFixture(
        source_name="manual_current_fixture",
        home_team="United States",
        away_team="Canada",
        match_date="2026-06-24",
    )
    assert fixture.to_dict()["home_team"] == "United States"
    assert determine_data_support_level(fixture=fixture) == "low_fixture_only"
    assert determine_data_support_level() == "insufficient"


def test_phase22_adapters_no_network_skip_or_warn():
    checks = [
        audit_openfootball_worldcup(allow_network=False)[0],
        audit_thestatsapi_worldcup(allow_network=False)[0],
        audit_sofascore_current_international(allow_network=False)[0],
        audit_eloratings_current(allow_network=False)[0],
        audit_espn_scoreboard(allow_network=False)[0],
        audit_fbref_international(allow_network=False),
    ]
    assert {result.status for result in checks}.issubset({"skipped", "warn", "success"})
    assert all(result.source_name for result in checks)


def test_phase22_manual_fallback_and_slate_builder(tmp_path):
    manual = ROOT / "data" / "sample" / "current_international_matchups.csv"
    fixtures = parse_manual_current_matchups(manual)
    assert len(fixtures) >= 2
    result = build_current_international_slate(
        as_of_date="2026-06-24",
        manual_matchups=manual,
        allow_network=False,
        output_dir=tmp_path,
    )
    slate = result["slate"]
    assert len(slate) >= 2
    assert {"home_team", "away_team", "data_support_level", "warnings"}.issubset(slate.columns)
    assert "low_fixture_only" in set(slate["data_support_level"])
    assert result["slate_path"].exists()
    assert result["source_summary_path"].exists()


def test_phase22_projection_wrapper_writes_outputs(tmp_path):
    manual = ROOT / "data" / "sample" / "current_international_matchups.csv"
    result = project_current_international(
        as_of_date="2026-06-24",
        manual_matchups=manual,
        allow_network=False,
        max_matches=1,
        output_dir=tmp_path,
    )
    projections = result["projections"]
    assert len(projections) == 1
    assert projections.iloc[0]["data_support_level"] == "low_fixture_only"
    assert "proxy_adjustments_enabled=false" in projections.iloc[0]["phase22_guardrails"]
    assert result["projection_report_path"].exists()
    report = result["projection_report_path"].read_text(encoding="utf-8").lower()
    assert "no betting recommendations" in report
    assert "not true event, tracking, xg" in report


def test_phase22_cli_commands_exist_and_run_no_network(tmp_path):
    parser = cli.build_parser()
    commands = parser._subparsers._group_actions[0].choices
    for command in [
        "audit-current-international",
        "build-current-international-slate",
        "project-current-international",
    ]:
        assert command in commands
    manual = ROOT / "data" / "sample" / "current_international_matchups.csv"
    for command in [
        ["audit-current-international", "--as-of-date", "2026-06-24", "--output-dir", str(tmp_path / "audit")],
        ["build-current-international-slate", "--manual-matchups", str(manual), "--as-of-date", "2026-06-24", "--output-dir", str(tmp_path / "slate")],
        ["project-current-international", "--manual-matchups", str(manual), "--as-of-date", "2026-06-24", "--max-matches", "1", "--output-dir", str(tmp_path / "project")],
    ]:
        result = subprocess.run([sys.executable, "-m", "src.cli", *command], cwd=ROOT, capture_output=True, text=True, check=True)
        assert "Manifest:" in result.stdout


def test_phase22_generated_outputs_are_ignored_and_guardrails_hold():
    ignored = subprocess.run(
        ["git", "check-ignore", "outputs/current_international/2026-06-24/current_international_slate.csv"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
    source_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in [
        "src/international_current/current_international_slate.py",
        "docs/CURRENT_INTERNATIONAL_DATA.md",
        "docs/WORLD_CUP_CURRENT_WORKFLOW.md",
    ])
    assert "Current StatsBomb is not used" in source_text
    assert "best bet" not in source_text.lower()
    assert "betting pick" not in source_text.lower()

