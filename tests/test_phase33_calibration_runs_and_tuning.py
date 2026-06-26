from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.baseline_calibration import calibrate_baseline_projections
from src.cli import build_parser
from src.international_current.current_international_slate import project_current_international
from src.international_current.current_international_schema import CurrentInternationalFixture, CurrentInternationalTeamRating
from src.international_current.rating_projection import project_from_fixture_and_ratings
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.run_index import build_run_index
from src.viewer.static_viewer import build_static_viewer


pytestmark = pytest.mark.quick


def _write_historical_cache(cache: Path) -> None:
    parsed = cache / "parsed"
    parsed.mkdir(parents=True, exist_ok=True)
    teams = ["Mexico", "Canada", "Japan", "Sweden"]
    snapshots = []
    for snapshot_date, offset in [("2020-12-31", 0), ("2021-12-31", 25)]:
        for index, team in enumerate(teams):
            snapshots.append({
                "snapshot_date": snapshot_date,
                "team_name": team,
                "normalized_team_name": team,
                "rating": 1600 + index * 80 + offset,
                "rating_source": "synthetic_snapshot",
                "rating_source_url": "local",
                "source_status": "cache_hit",
                "is_historical_snapshot": True,
                "snapshot_confidence": "synthetic_test",
                "warning": "",
            })
    results = []
    dates = pd.date_range("2021-01-15", periods=32, freq="21D")
    for index, match_date in enumerate(dates):
        home = teams[index % len(teams)]
        away = teams[(index + 1) % len(teams)]
        results.append({
            "match_date": match_date.date().isoformat(),
            "competition": "Synthetic International",
            "home_team": home,
            "away_team": away,
            "home_goals": [2, 1, 0, 3][index % 4],
            "away_goals": [1, 1, 2, 0][index % 4],
            "neutral_site": "true",
            "source_name": "synthetic_results",
            "source_url": "local",
            "source_status": "cache_hit",
            "is_result": True,
            "warning": "",
        })
    pd.DataFrame(snapshots).to_csv(parsed / "historical_rating_snapshots.csv", index=False)
    pd.DataFrame(results).to_csv(parsed / "historical_results.csv", index=False)


def _write_current_cache(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    fixtures = [
        {
            "source_match_id": "mex-can",
            "match_date": "2026-06-25",
            "kickoff_time": "20:00",
            "competition": "FIFA World Cup",
            "round_name": "Group Stage",
            "group_name": "Group A",
            "home_team": "Mexico",
            "away_team": "Canada",
            "neutral_site": "true",
            "status": "scheduled",
            "source_name": "local_fixture_cache",
            "source_tier": "real",
            "reliability_status": "local_cache",
        },
    ]
    ratings = [
        {"team": "Mexico", "rating": 1840, "rating_date": "2026-06-25", "rating_source": "synthetic_real_rating"},
        {"team": "Canada", "rating": 1740, "rating_date": "2026-06-25", "rating_source": "synthetic_real_rating"},
    ]
    with (cache / "fixtures.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fixtures[0].keys()))
        writer.writeheader()
        writer.writerows(fixtures)
    with (cache / "ratings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ratings[0].keys()))
        writer.writeheader()
        writer.writerows(ratings)


def _club_rows() -> pd.DataFrame:
    teams = ["AFC Red", "Bayside", "City Blue", "Dynamo"]
    rows = []
    for index, match_date in enumerate(pd.date_range("2024-08-01", periods=36, freq="7D")):
        rows.append({
            "date": match_date.date().isoformat(),
            "home_team": teams[index % len(teams)],
            "away_team": teams[(index + 2) % len(teams)],
            "home_goals": [2, 1, 0, 3][index % 4],
            "away_goals": [1, 0, 2, 1][index % 4],
        })
    return pd.DataFrame(rows)


def test_phase33_calibration_runs_do_not_overwrite_latest_and_index(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    outputs = tmp_path / "outputs" / "calibration"
    _write_historical_cache(cache)
    monkeypatch.setattr("src.analysis.baseline_calibration._load_club_historical", lambda max_rows=None: _club_rows())

    international = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="international_historical",
        min_rows=20,
        output_dir=outputs,
        cache_dir=cache,
    )
    club = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="club_historical",
        min_rows=12,
        output_dir=outputs,
    )
    second_international = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="international_historical",
        min_rows=20,
        output_dir=outputs,
        cache_dir=cache,
    )

    assert international["run_dir"] != second_international["run_dir"]
    assert Path(international["paths"]["manifest"]).exists()
    assert Path(club["paths"]["manifest"]).exists()
    assert (outputs / "2026-06-25" / "latest_manifest.json").exists()
    assert (outputs / "2026-06-25" / "international_historical" / "latest_manifest.json").exists()
    index = pd.read_csv(outputs / "2026-06-25" / "calibration_run_index.csv")
    assert len(index) == 3
    assert {"international_historical", "club_historical"}.issubset(set(index["data_source"]))
    manifest = json.loads(Path(second_international["paths"]["manifest"]).read_text(encoding="utf-8"))
    assert manifest["calibration_run_id"]
    assert manifest["calibration_data_source"] == "international_historical"
    assert manifest["calibration_config_hash"]
    assert manifest["baseline_tuning"]["status"] == "not_requested"


def test_phase33_tuning_grid_candidate_config_holdout_and_defaults(tmp_path):
    cache = tmp_path / "cache"
    outputs = tmp_path / "outputs" / "calibration"
    _write_historical_cache(cache)
    before = project_from_fixture_and_ratings(
        CurrentInternationalFixture(source_name="test_fixture", home_team="Mexico", away_team="Canada"),
        CurrentInternationalTeamRating(source_name="test_rating", team="Mexico", rating_value=1840),
        CurrentInternationalTeamRating(source_name="test_rating", team="Canada", rating_value=1740),
    )

    no_candidate = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="international_historical",
        min_rows=20,
        output_dir=outputs,
        cache_dir=cache,
        run_tuning=True,
        tuning_profile="small",
        primary_metric="composite",
    )
    assert not (Path(no_candidate["run_dir"]) / "baseline_tuning" / "candidate_model_config.json").exists()

    tuned = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="international_historical",
        min_rows=20,
        output_dir=outputs,
        cache_dir=cache,
        run_tuning=True,
        tuning_profile="small",
        primary_metric="composite",
        save_tuning_candidates=True,
        holdout_start_date="2022-01-01",
        holdout_end_date="2023-12-31",
        train_end_date="2021-12-31",
    )
    run_dir = Path(tuned["run_dir"])
    grid = pd.read_csv(run_dir / "baseline_tuning" / "baseline_tuning_grid.csv")
    best = pd.read_csv(run_dir / "baseline_tuning" / "baseline_tuning_best_candidates.csv")
    candidate_config = run_dir / "baseline_tuning" / "candidate_model_config.json"

    assert not grid.empty
    assert "composite_score" in grid.columns
    assert set(best["recommendation"]).issubset({
        "keep_current_baseline",
        "candidate_improves_wdl",
        "candidate_improves_totals",
        "candidate_balanced_improvement",
        "candidate_overfits_or_unstable",
        "insufficient_rows",
        "needs_holdout_validation",
        "totals_still_too_low",
        "totals_improved_wdl_hurt",
    })
    assert candidate_config.exists()
    assert (run_dir / "baseline_tuning" / "train_metrics.csv").exists()
    assert (run_dir / "baseline_tuning" / "holdout_metrics.csv").exists()
    payload = json.loads(candidate_config.read_text(encoding="utf-8"))
    assert payload["production_defaults_changed"] is False

    after = project_from_fixture_and_ratings(
        CurrentInternationalFixture(source_name="test_fixture", home_team="Mexico", away_team="Canada"),
        CurrentInternationalTeamRating(source_name="test_rating", team="Mexico", rating_value=1840),
        CurrentInternationalTeamRating(source_name="test_rating", team="Canada", rating_value=1740),
    )
    assert before["projected_home_xg"] == after["projected_home_xg"]
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False


def test_phase33_candidate_preview_and_viewer_index(tmp_path):
    historical_cache = tmp_path / "historical_cache"
    current_cache = tmp_path / "current_cache"
    outputs = tmp_path / "outputs"
    _write_historical_cache(historical_cache)
    _write_current_cache(current_cache)
    tuned = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="international_historical",
        min_rows=20,
        output_dir=outputs / "calibration",
        cache_dir=historical_cache,
        run_tuning=True,
        save_tuning_candidates=True,
    )
    candidate_config = Path(tuned["run_dir"]) / "baseline_tuning" / "candidate_model_config.json"

    projection = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=current_cache,
        output_dir=outputs / "current_international",
        slate_window="all-resolved",
        candidate_config=candidate_config,
    )
    preview = projection["candidate_preview"]
    preview_csv = Path(preview["paths"]["candidate_projection_comparison"])
    preview_rows = pd.read_csv(preview_csv)

    assert projection["manifest"]["output_paths"]["candidate_preview"]["status"] == "written"
    assert preview_csv.exists()
    assert {"baseline_team_a_xg", "candidate_team_a_xg", "probability_delta", "warning"}.issubset(preview_rows.columns)
    assert (outputs / "current_international" / "2026-06-25" / "current_international_projections.csv").exists()

    entries = build_run_index(outputs)
    assert any(entry["entry_type"] == "baseline_calibration" and entry["tuning_status"] == "diagnostic_only" for entry in entries)
    viewer = build_static_viewer(outputs, outputs / "viewer")
    html = (outputs / "viewer" / "index.html").read_text(encoding="utf-8")
    assert viewer["safety_scan_status"] == "pass"
    assert "tuning recommendation" in html.lower()
    detail = (outputs / "viewer" / "runs" / f"{projection['manifest'].get('run_id', 'current_international_2026-06-25')}.html")
    assert detail.exists()


def test_phase33_cli_flags_and_guardrails_registered():
    commands = build_parser()._subparsers._group_actions[0].choices
    calibration_help = commands["calibrate-baseline-projections"].format_help()
    projection_help = commands["project-current-international"].format_help()

    assert "--run-tuning" in calibration_help
    assert "--tuning-profile" in calibration_help
    assert "--primary-metric" in calibration_help
    assert "--save-tuning-candidates" in calibration_help
    assert "--apply-tuning" in calibration_help
    assert "--holdout-start-date" in calibration_help
    assert "--candidate-config" in projection_help
    assert "--candidate-config" not in commands["build-current-international-slate"].format_help()
    assert "run-today" in commands
    assert "validate-v1" in commands
