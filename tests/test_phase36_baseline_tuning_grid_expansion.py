from __future__ import annotations

import json
import sys
from pathlib import Path
from subprocess import run

import pandas as pd
import pytest

from src.analysis.baseline_tuning import (
    candidate_validation_status,
    evaluate_tuning_grid,
    project_candidate_xg,
    scoreline_candidate_label,
    tuning_grid,
)
from src.analysis.current_result_grading import grade_current_projections
from src.analysis.xg_formula_audit import _classify_line, audit_xg_formula
from src.cli import build_parser
from src.international_current.current_international_schema import CurrentInternationalFixture, CurrentInternationalTeamRating
from src.international_current.current_international_slate import _write_candidate_projection_preview
from src.international_current.rating_projection import project_from_fixture_and_ratings
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.run_index import build_run_index
from src.viewer.static_viewer import build_static_viewer


pytestmark = pytest.mark.quick


def _rows() -> pd.DataFrame:
    rows = []
    outcomes = [(2, 1), (0, 0), (1, 3), (3, 2), (1, 1), (0, 2)] * 4
    for index, (home_goals, away_goals) in enumerate(outcomes):
        rows.append({
            "date": f"2024-02-{index + 1:02d}",
            "home_team": f"Home {index}",
            "away_team": f"Away {index}",
            "home_goals": home_goals,
            "away_goals": away_goals,
            "home_rating": 1680 + (index % 6) * 45,
            "away_rating": 1600,
            "home_xg": 1.25,
            "away_xg": 1.05,
            "home_win_prob": 0.42,
            "draw_prob": 0.29,
            "away_win_prob": 0.29,
            "over_2_5_prob": 0.44,
            "btts_prob": 0.48,
        })
    return pd.DataFrame(rows)


def test_xg_audit_detects_caps_floors_and_safe_guards(tmp_path):
    found, recommendation, _ = _classify_line("home_xg = round(max(0.35, total * home_share), 3)", "production")
    assert found == "team xG floor"
    assert recommendation == "convert_to_config"

    found, recommendation, _ = _classify_line("return 5.0, True, 'lowered to broad sanity guard 5.00'", "production")
    assert found == "broad safety guard"
    assert recommendation == "keep_extreme_safety_guard"

    result = audit_xg_formula(as_of_date="2026-06-26", output_dir=tmp_path / "calibration")
    audit = result["audit"]
    assert Path(result["paths"]["xg_formula_audit"]).exists()
    assert {"file", "formula_area", "logic_type", "recommendation"}.issubset(audit.columns)
    assert "remove_cap" in set(audit["recommendation"]) or "convert_to_config" in set(audit["recommendation"])


def test_production_rating_projection_reports_only_broad_safety_guards():
    fixture = CurrentInternationalFixture(source_name="test", home_team="Favorite", away_team="Underdog")
    home = CurrentInternationalTeamRating(source_name="rating", team="Favorite", rating_value=2500)
    away = CurrentInternationalTeamRating(source_name="rating", team="Underdog", rating_value=1200)
    result = project_from_fixture_and_ratings(fixture, home, away)

    assert result["projected_home_xg"] > 1.65
    assert result["projected_away_xg"] >= 0.05
    assert "xg_safety_guard_applied" in result
    assert "xg_safety_guard_reason" in result


def test_tuning_grid_includes_no_floor_no_cap_candidates_and_expanded_metrics():
    grid = tuning_grid("small")
    assert any(candidate["underdog_xg_floor"] == 0.0 for candidate in grid)
    assert all("scoreline_dispersion_multiplier" in candidate for candidate in grid)
    assert all("underdog_xg_scale" in candidate for candidate in grid)

    evaluated, best = evaluate_tuning_grid(_rows(), profile="small")
    assert not evaluated.empty
    assert not best.empty
    expected = {
        "predicted_actual_total_delta",
        "favorite_2plus_calibration_gap",
        "underdog_2plus_calibration_gap",
        "goal_band_0_calibration_gap",
        "goal_band_1_calibration_gap",
        "goal_band_2_calibration_gap",
        "goal_band_3plus_calibration_gap",
        "candidate_validation_status",
    }
    assert expected.issubset(evaluated.columns)


def test_candidate_labels_are_cautious_for_wdl_harm_and_balanced_for_stable_spread():
    baseline = {"wdl_log_loss": 1.0, "total_goals_mae": 1.5, "over_under_2_5_brier_score": 0.25}
    hurt = {
        "rows": 100,
        "wdl_log_loss": 1.08,
        "total_goals_mae": 1.3,
        "over_2_5_brier": 0.22,
        "top_5_correct_score_hit_rate_delta": 0.01,
        "actual_score_rank_average_delta": -0.2,
        "mean_projected_total": 2.8,
        "predicted_actual_total_delta": 0.1,
    }
    assert scoreline_candidate_label(hurt, baseline) == "totals_improved_wdl_hurt"
    assert candidate_validation_status(hurt, baseline) in {"overfit_risk", "totals_improved_wdl_hurt"}

    balanced = dict(hurt, wdl_log_loss=0.995, over_2_5_brier=0.245, top_5_correct_score_hit_rate_delta=0.03)
    assert scoreline_candidate_label(balanced, baseline) == "balanced_improvement"


def test_candidate_preview_and_grading_comparison_outputs(tmp_path):
    candidate = project_candidate_xg(1750, 1600, {"baseline_total_goals": 2.65, "underdog_xg_floor": 0.0})
    config_path = tmp_path / "candidate_scoreline_model_config.json"
    config_path.write_text(json.dumps({
        "config_type": "diagnostic_scoreline_candidate_model_config",
        "production_defaults_changed": False,
        "model_parameters": {"baseline_total_goals": 2.65, "underdog_xg_floor": 0.0},
        "best_candidate_metrics": candidate,
    }), encoding="utf-8")
    projections = pd.DataFrame([{
        "fixture_date": "2026-06-25",
        "team_a": "Curacao",
        "team_b": "Cote d'Ivoire",
        "team_a_xg_final": 0.9,
        "team_b_xg_final": 1.35,
        "projected_total": 2.25,
        "most_likely_score": "0 - 1",
        "team_a_win_prob": 0.25,
        "draw_prob": 0.29,
        "team_b_win_prob": 0.46,
        "home_rating": 1500,
        "away_rating": 1700,
    }])
    preview = _write_candidate_projection_preview(tmp_path / "current" / "2026-06-26", projections, config_path)
    preview_rows = pd.read_csv(preview["paths"]["scoreline_candidate_projection_comparison"])
    assert {"delta_btts_probability", "delta_over_2_5_probability", "delta_home_win_probability"}.issubset(preview_rows.columns)
    assert Path(preview["paths"]["scoreline_candidate_projection_summary"]).exists()

    projection_path = tmp_path / "projection.csv"
    actual_path = tmp_path / "actual.csv"
    projections.to_csv(projection_path, index=False)
    pd.DataFrame([{
        "fixture_date": "2026-06-25",
        "home_team": "Curacao",
        "away_team": "Cote d'Ivoire",
        "home_goals": 0,
        "away_goals": 2,
        "source_name": "manual_test",
    }]).to_csv(actual_path, index=False)
    graded = grade_current_projections(
        as_of_date="2026-06-25",
        projection_file=projection_path,
        actual_results=actual_path,
        output_dir=tmp_path / "grading",
        candidate_config=config_path,
    )
    comparison = graded["manifest"]["candidate_grading_comparison"]
    assert comparison["status"] == "written"
    assert Path(comparison["paths"]["candidate_grading_comparison"]).exists()


def test_viewer_indexes_xg_audit_and_guardrails(tmp_path):
    audit_xg_formula(as_of_date="2026-06-26", output_dir=tmp_path / "outputs" / "calibration")
    entries = build_run_index(tmp_path / "outputs")
    assert any(entry["entry_type"] == "xg_formula_audit" for entry in entries)
    viewer = build_static_viewer(tmp_path / "outputs", tmp_path / "viewer")
    assert viewer["safety_scan_status"] == "pass"
    html = (tmp_path / "viewer" / "index.html").read_text(encoding="utf-8")
    assert "xg_formula_audit" in html
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
    assert "validate-v1" in build_parser()._subparsers._group_actions[0].choices
    assert "run-today" in build_parser()._subparsers._group_actions[0].choices


def test_validate_v1_still_passes():
    result = run([sys.executable, "-m", "src.cli", "validate-v1"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

