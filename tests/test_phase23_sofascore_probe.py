from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import src.cli as cli
from src.data_sources.adapters.sofascore_adapter import (
    audit_sofascore_current_international,
    parse_fixtures,
    parse_lineup_availability,
    parse_match_statistics,
    probe_sofascore,
    read_cached_json,
    write_cached_json,
)
from src.international_current.current_international_slate import (
    build_current_international_slate,
    project_current_international,
)
from src.operational.defaults import OPERATIONAL_DEFAULTS


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.quick


def _fixture_payload() -> dict:
    return {
        "events": [
            {
                "id": 12345,
                "startTimestamp": 1782259200,
                "tournament": {"name": "FIFA World Cup", "category": {"name": "International"}},
                "season": {"name": "2026"},
                "homeTeam": {"name": "United States"},
                "awayTeam": {"name": "Canada"},
                "status": {"type": "notstarted"},
                "roundInfo": {"name": "Group Stage"},
                "venue": {"stadium": {"name": "Sample Stadium"}},
            }
        ]
    }


def _stats_payload(include_xg: bool = False) -> dict:
    items = [
        {"name": "Ball possession", "homeValue": "55%", "awayValue": "45%"},
        {"name": "Total shots", "homeValue": 12, "awayValue": 8},
        {"name": "Shots on target", "homeValue": 5, "awayValue": 3},
        {"name": "Corner kicks", "homeValue": 6, "awayValue": 2},
        {"name": "Fouls", "homeValue": 9, "awayValue": 11},
        {"name": "Yellow cards", "homeValue": 1, "awayValue": 2},
    ]
    if include_xg:
        items.extend([
            {"name": "Expected goals", "homeValue": 1.4, "awayValue": 0.7},
            {"name": "Expected goals on target", "homeValue": 1.1, "awayValue": 0.4},
        ])
    return {"statistics": [{"groups": [{"statisticsItems": items}]}]}


def test_sofascore_no_network_audit_skips_without_crash(tmp_path):
    result, fixtures, stats = audit_sofascore_current_international(
        allow_network=False,
        as_of_date="2026-06-24",
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "outputs",
    )
    assert result.status == "skipped"
    assert fixtures == []
    assert stats == []
    assert "fixtures" in result.fields_missing


def test_parse_synthetic_fixture_payload():
    fixtures = parse_fixtures(_fixture_payload(), competition="World Cup")
    assert len(fixtures) == 1
    fixture = fixtures[0]
    assert fixture.source_name == "sofascore"
    assert fixture.source_match_id == "12345"
    assert fixture.home_team == "United States"
    assert fixture.away_team == "Canada"
    assert fixture.status == "scheduled"


def test_parse_synthetic_stats_without_fake_xg():
    stats = parse_match_statistics(_stats_payload(include_xg=False), match_id="12345")
    assert stats is not None
    assert stats.shots_home == 12
    assert stats.shots_on_target_home == 5
    assert stats.xg_home is None
    assert stats.xgot_home is None
    assert stats.data_mode == "current_fixture_stats"


def test_parse_synthetic_stats_with_xg_and_xgot():
    stats = parse_match_statistics(_stats_payload(include_xg=True), match_id="12345")
    assert stats is not None
    assert stats.xg_home == 1.4
    assert stats.xg_away == 0.7
    assert stats.xgot_home == 1.1
    assert stats.xgot_away == 0.4
    assert stats.data_mode == "current_fixture_xg"


def test_parse_lineup_and_player_rating_availability():
    lineups, ratings = parse_lineup_availability({
        "confirmed": True,
        "home": {"players": [{"player": {"name": "A"}, "statistics": {"rating": 7.2}}]},
        "away": {"players": [{"player": {"name": "B"}, "statistics": {}}]},
    })
    assert lineups is True
    assert ratings is True


def test_cache_helper_round_trip(tmp_path):
    written = write_cached_json(tmp_path, "fixtures", "2026-06-24", _fixture_payload())
    payload, path = read_cached_json(tmp_path, "fixtures", "2026-06-24")
    assert path == written
    assert payload is not None
    assert payload["events"][0]["id"] == 12345


def test_probe_sofascore_reads_cache_and_writes_outputs(tmp_path):
    cache = tmp_path / "cache"
    write_cached_json(cache, "fixtures", "2026-06-24_FIFA World Cup_", _fixture_payload())
    write_cached_json(cache, "match_statistics", "12345", _stats_payload(include_xg=True))
    write_cached_json(cache, "lineups", "12345", {
        "home": {"players": [{"statistics": {"rating": 7.0}}]},
        "away": {"players": []},
    })
    result = probe_sofascore(
        as_of_date="2026-06-24",
        competition="FIFA World Cup",
        allow_network=False,
        cache_dir=cache,
        output_dir=tmp_path / "outputs",
        max_matches=1,
    )
    assert result["manifest"]["fixture_count"] == 1
    assert result["manifest"]["match_stats_count"] == 1
    assert result["manifest"]["xg_found"] is True
    assert result["manifest"]["lineups_found"] is True
    assert result["fixture_path"].exists()
    assert result["match_stats_path"].exists()
    assert result["summary_path"].exists()


def test_probe_sofascore_cli_exists_and_no_network_works(tmp_path):
    parser = cli.build_parser()
    assert "probe-sofascore" in parser._subparsers._group_actions[0].choices
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "probe-sofascore",
            "--as-of-date",
            "2026-06-24",
            "--no-network",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--output-dir",
            str(tmp_path / "outputs"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "SofaScore probe summary:" in result.stdout
    assert "Fixtures found: 0" in result.stdout


def test_current_international_manual_workflows_still_work(tmp_path):
    manual = ROOT / "data" / "sample" / "current_international_matchups.csv"
    slate = build_current_international_slate(
        as_of_date="2026-06-24",
        manual_matchups=manual,
        allow_network=False,
        output_dir=tmp_path / "slate",
    )
    assert len(slate["slate"]) >= 2
    projection = project_current_international(
        as_of_date="2026-06-24",
        manual_matchups=manual,
        allow_network=False,
        output_dir=tmp_path / "projection",
        max_matches=1,
    )
    assert len(projection["projections"]) == 1


def test_phase23_guardrails_and_ignored_outputs():
    ignored = subprocess.run(
        ["git", "check-ignore", "outputs/source_probes/sofascore/2026-06-24/sofascore_probe_summary.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0
    cache_ignored = subprocess.run(
        ["git", "check-ignore", "data/source_cache/sofascore/example.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert cache_ignored.returncode == 0
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
    source_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in [
        "src/data_sources/adapters/sofascore_adapter.py",
        "docs/SOFASCORE_CURRENT_PROBE.md",
        "docs/CURRENT_INTERNATIONAL_DATA.md",
    ])
    assert "Current StatsBomb is not used" in source_text
    assert "best bet" not in source_text.lower()
    assert "betting pick" not in source_text.lower()

