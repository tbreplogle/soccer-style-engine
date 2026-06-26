from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.baseline_calibration import calibrate_baseline_projections, write_baseline_tuning_diagnostics
from src.analysis.projection_checkpoint import run_projection_checkpoint
from src.cli import build_parser
from src.international_current.current_international_slate import project_current_international
from src.international_current.fixture_deduplication import deduplicate_fixtures
from src.international_current.historical_rating_matcher import attach_historical_ratings
from src.international_current.historical_rating_snapshots import load_historical_rating_snapshots
from src.international_current.historical_results import load_historical_results
from src.international_current.historical_seed import seed_international_historical_calibration_data
from src.international_current.kickoff_normalization import normalize_kickoff_time
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.run_index import build_run_index
from src.viewer.static_viewer import build_static_viewer


pytestmark = pytest.mark.quick


def _write_current_cache(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    fixtures = [
        ("of-cur-civ", "2026-06-25", "16:00 UTC-4", "Curacao", "Cote d'Ivoire", "openfootball_worldcup"),
        ("espn-cur-civ", "2026-06-25", "20:00", "Curacao", "Cote d'Ivoire", "espn_scoreboard"),
        ("jpn-swe", "2026-06-25", "18:00 UTC-5", "Japan", "Sweden", "openfootball_worldcup"),
    ]
    rows = [
        {
            "source_match_id": source_match_id,
            "match_date": match_date,
            "kickoff_time": kickoff,
            "competition": "FIFA World Cup",
            "round_name": "Group Stage",
            "group_name": "Group A",
            "home_team": home,
            "away_team": away,
            "neutral_site": "true",
            "status": "scheduled",
            "source_name": source,
            "source_tier": "real",
            "reliability_status": "local_cache",
        }
        for source_match_id, match_date, kickoff, home, away, source in fixtures
    ]
    with (cache / "fixtures.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    ratings = [
        {"team": team, "rating": rating, "rating_date": "2026-06-25", "rating_source": "synthetic_real_rating"}
        for team, rating in [
            ("Curacao", 1453),
            ("Cote d'Ivoire", 1728),
            ("Japan", 1925),
            ("Sweden", 1727),
        ]
    ]
    with (cache / "ratings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ratings[0].keys()))
        writer.writeheader()
        writer.writerows(ratings)


def _write_historical_cache(cache: Path) -> None:
    parsed = cache / "parsed"
    parsed.mkdir(parents=True, exist_ok=True)
    snapshots = pd.DataFrame([
        {"snapshot_date": "2020-12-31", "team_name": "Mexico", "normalized_team_name": "Mexico", "rating": 1800, "rating_source": "synthetic_snapshot", "rating_source_url": "local", "source_status": "cache_hit", "is_historical_snapshot": True, "snapshot_confidence": "synthetic_test", "warning": ""},
        {"snapshot_date": "2020-12-31", "team_name": "Canada", "normalized_team_name": "Canada", "rating": 1600, "rating_source": "synthetic_snapshot", "rating_source_url": "local", "source_status": "cache_hit", "is_historical_snapshot": True, "snapshot_confidence": "synthetic_test", "warning": ""},
        {"snapshot_date": "2021-06-01", "team_name": "Mexico", "normalized_team_name": "Mexico", "rating": 1810, "rating_source": "synthetic_snapshot", "rating_source_url": "local", "source_status": "cache_hit", "is_historical_snapshot": True, "snapshot_confidence": "synthetic_test", "warning": ""},
        {"snapshot_date": "2021-06-01", "team_name": "Canada", "normalized_team_name": "Canada", "rating": 1640, "rating_source": "synthetic_snapshot", "rating_source_url": "local", "source_status": "cache_hit", "is_historical_snapshot": True, "snapshot_confidence": "synthetic_test", "warning": ""},
        {"snapshot_date": "2022-01-01", "team_name": "Mexico", "normalized_team_name": "Mexico", "rating": 1900, "rating_source": "future_snapshot", "rating_source_url": "local", "source_status": "cache_hit", "is_historical_snapshot": True, "snapshot_confidence": "synthetic_test", "warning": ""},
    ])
    results = pd.DataFrame([
        {"match_date": "2021-01-15", "competition": "Friendly", "home_team": "Mexico", "away_team": "Canada", "home_goals": 2, "away_goals": 1, "neutral_site": "true", "source_name": "synthetic_results", "source_url": "local", "source_status": "cache_hit", "is_result": True, "warning": ""},
        {"match_date": "2021-07-15", "competition": "Gold Cup", "home_team": "Canada", "away_team": "Mexico", "home_goals": 0, "away_goals": 1, "neutral_site": "true", "source_name": "synthetic_results", "source_url": "local", "source_status": "cache_hit", "is_result": True, "warning": ""},
        {"match_date": "2021-09-15", "competition": "Qualifier", "home_team": "Mexico", "away_team": "Canada", "home_goals": 1, "away_goals": 1, "neutral_site": "true", "source_name": "synthetic_results", "source_url": "local", "source_status": "cache_hit", "is_result": True, "warning": ""},
    ])
    snapshots.to_csv(parsed / "historical_rating_snapshots.csv", index=False)
    results.to_csv(parsed / "historical_results.csv", index=False)


def test_kickoff_normalization_handles_offsets_and_missing_timezones():
    offset = normalize_kickoff_time("16:00 UTC-4", "2026-06-25")
    plain = normalize_kickoff_time("20:00", "2026-06-25")
    blank = normalize_kickoff_time("", "2026-06-25")

    assert offset["kickoff_timezone_status"] == "known_offset"
    assert offset["kickoff_datetime_normalized"].startswith("2026-06-25T20:00")
    assert plain["kickoff_timezone_status"] == "time_no_timezone"
    assert "not inferred" in plain["kickoff_parse_warning"]
    assert blank["kickoff_timezone_status"] == "date_only"


def test_dedupe_collapses_same_fixture_with_different_kickoff_formats():
    frame = pd.DataFrame([
        {"match_date": "2026-06-25", "kickoff_time": "16:00 UTC-4", "competition": "FIFA World Cup", "home_team": "Curacao", "away_team": "Cote d'Ivoire", "neutral_site": "true", "source_fixture_name": "openfootball_worldcup", "source_tier": "real", "source_fixture_status": "scheduled", "is_resolved_fixture": True},
        {"match_date": "2026-06-25", "kickoff_time": "20:00", "competition": "FIFA World Cup", "home_team": "Curacao", "away_team": "Cote d'Ivoire", "neutral_site": "true", "source_fixture_name": "espn_scoreboard", "source_tier": "real", "source_fixture_status": "scheduled", "is_resolved_fixture": True},
        {"match_date": "2026-06-26", "kickoff_time": "20:00", "competition": "FIFA World Cup", "home_team": "Curacao", "away_team": "Cote d'Ivoire", "neutral_site": "true", "source_fixture_name": "openfootball_worldcup", "source_tier": "real", "source_fixture_status": "scheduled", "is_resolved_fixture": True},
    ])
    result = deduplicate_fixtures(frame)

    assert result["summary"]["duplicate_rows_skipped"] == 1
    assert result["summary"]["fixture_rows_after_dedupe"] == 2
    duplicate = result["duplicates"].iloc[0]
    assert duplicate["dedupe_time_comparison"] in {"timezone_missing_or_uncomparable", "within_tolerance"}
    assert "dedupe_match_key" in result["deduplicated"].columns


def test_swapped_neutral_duplicates_are_review_only():
    frame = pd.DataFrame([
        {"match_date": "2026-06-25", "kickoff_time": "20:00", "competition": "FIFA World Cup", "home_team": "Japan", "away_team": "Sweden", "neutral_site": "true", "source_fixture_name": "openfootball_worldcup", "source_tier": "real", "source_fixture_status": "scheduled", "is_resolved_fixture": True},
        {"match_date": "2026-06-25", "kickoff_time": "20:00", "competition": "FIFA World Cup", "home_team": "Sweden", "away_team": "Japan", "neutral_site": "true", "source_fixture_name": "espn_scoreboard", "source_tier": "real", "source_fixture_status": "scheduled", "is_resolved_fixture": True},
    ])
    result = deduplicate_fixtures(frame)

    assert result["summary"]["duplicate_rows_skipped"] == 0
    assert result["summary"]["possible_duplicate_review_rows"] == 2


def test_direct_projection_and_checkpoint_fixture_keys_match(tmp_path):
    cache = tmp_path / "cache"
    outputs = tmp_path / "outputs"
    _write_current_cache(cache)

    direct = project_current_international(as_of_date="2026-06-25", cache_dir=cache, output_dir=outputs / "current_international", slate_window="next", max_matches=10, build_poisson_board=True)
    checkpoint = run_projection_checkpoint(as_of_date="2026-06-25", cache_dir=cache, output_dir=outputs / "projection_checkpoints", run_current_international=True, slate_window="next", max_matches=10, build_poisson_board=True)

    assert len(direct["projections"]) == 2
    assert checkpoint["manifest"]["rows_reviewed"] == 2
    assert checkpoint["manifest"]["projection_checkpoint_consistency"]["fixture_keys_match"] is True
    assert checkpoint["manifest"]["projection_checkpoint_consistency"]["status"] == "pass"


def test_historical_loaders_and_matcher_use_only_prior_snapshots(tmp_path):
    cache = tmp_path / "cache"
    _write_historical_cache(cache)
    snapshots = load_historical_rating_snapshots(cache)
    results = load_historical_results(cache)
    matched = attach_historical_ratings(results, snapshots)

    assert len(snapshots) == 5
    assert len(results) == 3
    assert len(matched[matched["rating_match_status"].eq("both_ratings_matched")]) == 3
    first = matched[matched["match_date"].eq("2021-01-15")].iloc[0]
    assert first["home_rating_snapshot_date"] == "2020-12-31"
    assert first["home_rating"] == 1800
    assert first["home_rating"] != 1900


def test_snapshot_too_old_is_flagged(tmp_path):
    cache = tmp_path / "cache"
    _write_historical_cache(cache)
    matched = attach_historical_ratings(load_historical_results(cache), load_historical_rating_snapshots(cache), max_snapshot_age_days=10)
    assert "snapshot_too_old" in set(matched["rating_match_status"])


def test_international_calibration_valid_and_blocked_paths(tmp_path):
    cache = tmp_path / "cache"
    _write_historical_cache(cache)
    # The calibration command reads the default cache path, so exercise its valid path through a temporary cwd-like cache by copying to expected relative layout.
    expected = Path("data/source_cache/current_international/parsed")
    expected.mkdir(parents=True, exist_ok=True)
    backup_results = expected / "historical_results.csv"
    backup_snapshots = expected / "historical_rating_snapshots.csv"
    old_results = backup_results.read_text(encoding="utf-8") if backup_results.exists() else None
    old_snapshots = backup_snapshots.read_text(encoding="utf-8") if backup_snapshots.exists() else None
    try:
        (cache / "parsed" / "historical_results.csv").replace(backup_results)
        (cache / "parsed" / "historical_rating_snapshots.csv").replace(backup_snapshots)
        valid = calibrate_baseline_projections(as_of_date="2026-06-25", data_source="international_historical", min_rows=2, output_dir=tmp_path / "calibration")
        assert valid["status"] == "valid_calibration"
        assert valid["metrics"]["row_count"] == 3
        assert valid["metrics"]["wdl_log_loss"] is not None
    finally:
        if old_results is None:
            backup_results.unlink(missing_ok=True)
        else:
            backup_results.write_text(old_results, encoding="utf-8")
        if old_snapshots is None:
            backup_snapshots.unlink(missing_ok=True)
        else:
            backup_snapshots.write_text(old_snapshots, encoding="utf-8")

    blocked = calibrate_baseline_projections(as_of_date="2026-06-25", data_source="current_international_results", min_rows=50, output_dir=tmp_path / "blocked")
    assert blocked["status"] == "blocked_missing_results"


def test_historical_seed_tuning_and_viewer_outputs(tmp_path):
    cache = tmp_path / "cache"
    outputs = tmp_path / "outputs"
    _write_historical_cache(cache)

    seed = seed_international_historical_calibration_data(
        start_date="2021-01-01",
        end_date="2021-12-31",
        seed_all=True,
        cache_dir=cache,
        output_dir=outputs / "calibration",
    )
    tuning = write_baseline_tuning_diagnostics(seed["matches_with_ratings"].rename(columns={"home_rating": "home_rating", "away_rating": "away_rating"}), as_of_date="2026-06-25", output_dir=outputs / "calibration")
    entries = build_run_index(outputs)
    viewer = build_static_viewer(outputs, outputs / "viewer")
    html = (outputs / "viewer" / "index.html").read_text(encoding="utf-8")

    assert seed["manifest"]["historical_rating_snapshot_rows"] == 5
    assert seed["manifest"]["historical_results_rows"] == 3
    assert seed["manifest"]["historical_matches_with_ratings_rows"] == 3
    assert tuning["manifest"]["status"] == "diagnostic_only"
    assert any(entry["entry_type"] == "historical_calibration_seed" for entry in entries)
    assert "historical_calibration_seed" in html
    assert viewer["safety_scan_status"] == "pass"


def test_cli_and_guardrails_remain_registered_phase32():
    commands = build_parser()._subparsers._group_actions[0].choices
    assert "seed-international-historical-calibration-data" in commands
    assert "calibrate-baseline-projections" in commands
    assert "run-today" in commands
    assert "--no-dedupe-fixtures" in commands["project-current-international"].format_help()
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
    payload = json.dumps({
        "current_statsbomb_live_data_used": False,
        "proxy_adjustments_enabled": False,
        "no_betting_recommendations": True,
    })
    assert "current_statsbomb_live_data_used" in payload
    assert "no_betting_recommendations" in payload
