from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.baseline_calibration import calibrate_baseline_projections
from src.cli import build_parser
from src.club.league_readiness import check_league_readiness
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.run_index import build_run_index
from src.viewer.static_viewer import build_static_viewer


pytestmark = pytest.mark.quick


def _club_history(path: Path, *, leagues: list[str] | None = None, rows_per_league: int = 36) -> pd.DataFrame:
    leagues = leagues or ["E0", "E1"]
    rows = []
    for league in leagues:
        teams = [f"{league} Alpha", f"{league} Beta", f"{league} City", f"{league} United"]
        for index, match_date in enumerate(pd.date_range("2024-08-01", periods=rows_per_league, freq="7D")):
            rows.append({
                "match_id": f"{league}-{index}",
                "date": match_date.date().isoformat(),
                "league": league,
                "league_name": league,
                "season": "2024-2025" if index < rows_per_league // 2 else "2025-2026",
                "home_team": teams[index % len(teams)],
                "away_team": teams[(index + 1) % len(teams)],
                "home_goals": [2, 1, 0, 3][index % 4],
                "away_goals": [1, 1, 2, 0][index % 4],
            })
    frame = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def _club_current(path: Path, *, future: bool = True) -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2026-06-01", periods=8, freq="7D") if future else pd.date_range("2026-04-01", periods=8, freq="7D")
    for league in ["E0", "E1"]:
        for index, match_date in enumerate(dates):
            rows.append({
                "match_id": f"current-{league}-{index}",
                "date": match_date.date().isoformat() if index < 6 or not future else "2026-07-10",
                "league": league,
                "league_name": league,
                "season": "2025-2026",
                "home_team": f"{league} Alpha" if index % 2 == 0 else f"{league} City",
                "away_team": f"{league} Beta" if index % 2 == 0 else f"{league} United",
                "home_goals": [2, 1, 0, 3, 1, 2, None, None][index],
                "away_goals": [1, 1, 2, 0, 0, 1, None, None][index],
                "home_shots": 10,
                "away_shots": 8,
                "home_shots_on_target": 4,
                "away_shots_on_target": 3,
                "home_corners": 5,
                "away_corners": 4,
            })
    frame = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def _patch_club_paths(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr("src.analysis.baseline_calibration.CLUB_HISTORICAL_PATHS", [path])


def test_phase34_club_calibration_diagnostics_and_filter_breakdown(tmp_path, monkeypatch):
    historical = tmp_path / "processed" / "multi_season_match_results.csv"
    _club_history(historical, rows_per_league=24)
    _patch_club_paths(monkeypatch, historical)

    result = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="club_historical",
        min_rows=20,
        max_rows=5,
        output_dir=tmp_path / "outputs" / "calibration",
    )
    run_dir = Path(result["run_dir"])
    diagnostics = (run_dir / "club_calibration_diagnostics.md").read_text(encoding="utf-8")
    breakdown = pd.read_csv(run_dir / "club_calibration_filter_breakdown.csv")

    assert result["status"] == "blocked_insufficient_rows"
    assert "Paths Checked" in diagnostics
    assert str(historical) in diagnostics
    assert "max_rows" in diagnostics
    assert "eligible_prior_history" in set(breakdown["step"])
    assert int(breakdown.loc[breakdown["step"].eq("eligible_prior_history"), "rows"].iloc[0]) > 5


def test_phase34_club_calibration_writes_league_and_season_outputs(tmp_path, monkeypatch):
    historical = tmp_path / "processed" / "multi_season_match_results.csv"
    _club_history(historical, leagues=["E0", "E1", "SP1"], rows_per_league=40)
    _patch_club_paths(monkeypatch, historical)

    result = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="club_historical",
        min_rows=30,
        output_dir=tmp_path / "outputs" / "calibration",
    )
    run_dir = Path(result["run_dir"])
    league = pd.read_csv(run_dir / "league_calibration_summary.csv")
    season = pd.read_csv(run_dir / "season_calibration_summary.csv")
    league_season = pd.read_csv(run_dir / "league_season_calibration_summary.csv")

    assert result["status"] == "valid_calibration"
    assert result["metrics"]["row_count"] > 30
    assert {"E0", "E1", "SP1"}.issubset(set(league["league"]))
    assert not season.empty
    assert not league_season.empty
    assert (run_dir.parent.parent / "calibration_comparison_summary.md").exists()


def test_phase34_club_tuning_diagnostic_outputs_do_not_change_defaults(tmp_path, monkeypatch):
    historical = tmp_path / "processed" / "multi_season_match_results.csv"
    _club_history(historical, rows_per_league=40)
    _patch_club_paths(monkeypatch, historical)

    result = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="club_historical",
        min_rows=20,
        output_dir=tmp_path / "outputs" / "calibration",
        run_tuning=True,
        tuning_profile="small",
        primary_metric="composite",
        save_tuning_candidates=True,
    )
    tuning_dir = Path(result["run_dir"]) / "baseline_tuning"
    manifest = json.loads((tuning_dir / "baseline_tuning_manifest.json").read_text(encoding="utf-8"))

    assert (tuning_dir / "baseline_tuning_grid.csv").exists()
    assert (tuning_dir / "baseline_tuning_best_candidates.csv").exists()
    assert (tuning_dir / "candidate_model_config.json").exists()
    assert manifest["diagnostic_only"] is True
    assert manifest["production_defaults_changed"] is False
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False


def test_phase34_league_readiness_ready_blocked_and_warning_statuses(tmp_path, monkeypatch):
    historical = tmp_path / "processed" / "multi_season_match_results.csv"
    current = tmp_path / "processed" / "multi_league_current_match_results.csv"
    _club_history(historical, rows_per_league=40)
    _club_current(current, future=True)
    _patch_club_paths(monkeypatch, historical)
    calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="club_historical",
        min_rows=20,
        output_dir=tmp_path / "outputs" / "calibration",
    )

    ready = check_league_readiness(
        as_of_date="2026-06-25",
        leagues=["E0", "E1"],
        require_calibration=True,
        require_current_fixtures=True,
        current_input=current,
        historical_input=historical,
        calibration_root=tmp_path / "outputs" / "calibration",
        output_dir=tmp_path / "outputs" / "club",
    )
    assert ready["status"] == "ready"
    assert ready["manifest"]["current_statsbomb_live_data_used"] is False

    missing_historical = check_league_readiness(
        as_of_date="2026-06-25",
        leagues=["E0"],
        current_input=current,
        historical_input=tmp_path / "missing.csv",
        output_dir=tmp_path / "missing_outputs" / "club",
    )
    assert missing_historical["status"] == "blocked_missing_historical_data"

    no_future_current = tmp_path / "processed" / "current_no_future.csv"
    _club_current(no_future_current, future=False)
    warning = check_league_readiness(
        as_of_date="2026-06-25",
        leagues=["E0"],
        current_input=no_future_current,
        historical_input=historical,
        calibration_root=tmp_path / "outputs" / "calibration",
        output_dir=tmp_path / "warning_outputs" / "club",
    )
    assert warning["status"] == "ready_with_warnings"
    strict = check_league_readiness(
        as_of_date="2026-06-25",
        leagues=["E0"],
        require_current_fixtures=True,
        current_input=no_future_current,
        historical_input=historical,
        calibration_root=tmp_path / "outputs" / "calibration",
        output_dir=tmp_path / "strict_outputs" / "club",
    )
    assert strict["status"] == "blocked_missing_current_fixtures"


def test_phase34_viewer_indexes_club_calibration_and_readiness(tmp_path, monkeypatch):
    historical = tmp_path / "processed" / "multi_season_match_results.csv"
    current = tmp_path / "processed" / "multi_league_current_match_results.csv"
    _club_history(historical, rows_per_league=40)
    _club_current(current, future=True)
    _patch_club_paths(monkeypatch, historical)
    calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="club_historical",
        min_rows=20,
        output_dir=tmp_path / "outputs" / "calibration",
    )
    check_league_readiness(
        as_of_date="2026-06-25",
        leagues=["E0", "E1"],
        current_input=current,
        historical_input=historical,
        calibration_root=tmp_path / "outputs" / "calibration",
        output_dir=tmp_path / "outputs" / "club",
    )

    entries = build_run_index(tmp_path / "outputs")
    viewer = build_static_viewer(tmp_path / "outputs", tmp_path / "viewer")
    html = (tmp_path / "viewer" / "index.html").read_text(encoding="utf-8")

    assert any(entry["entry_type"] == "baseline_calibration" and entry["calibration_data_source"] == "club_historical" for entry in entries)
    assert any(entry["entry_type"] == "club_league_readiness" for entry in entries)
    assert viewer["safety_scan_status"] == "pass"
    assert "club_league_readiness" in html


def test_phase34_cli_and_guardrails_registered():
    commands = build_parser()._subparsers._group_actions[0].choices
    readiness_help = commands["check-league-readiness"].format_help()

    assert "--require-calibration" in readiness_help
    assert "--require-current-fixtures" in readiness_help
    assert "validate-v1" in commands
    assert "run-today" in commands
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
