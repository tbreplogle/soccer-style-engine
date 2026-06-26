from __future__ import annotations

import json
import sys
from pathlib import Path
from subprocess import run

import pandas as pd
import pytest

from src.analysis.current_result_grading import grade_current_projections, grade_projection_rows, load_manual_results
from src.analysis.scoreline_calibration import evaluate_scoreline_calibration, scoreline_rankings, write_scoreline_diagnostics
from src.analysis.baseline_tuning import evaluate_tuning_grid, project_rows_with_candidate
from src.cli import build_parser
from src.international_current.current_international_slate import _write_candidate_projection_preview
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.run_index import build_run_index
from src.viewer.static_viewer import build_static_viewer


pytestmark = pytest.mark.quick


def _calibration_rows() -> pd.DataFrame:
    rows = []
    for index, (home_goals, away_goals) in enumerate([(2, 1), (0, 0), (1, 3), (3, 2), (1, 1), (0, 2)] * 4):
        rows.append({
            "date": f"2024-01-{index + 1:02d}",
            "fixture_date": f"2024-01-{index + 1:02d}",
            "home_team": f"Home {index}",
            "away_team": f"Away {index}",
            "home_goals": home_goals,
            "away_goals": away_goals,
            "home_xg": 1.25,
            "away_xg": 1.05,
            "home_win_prob": 0.42,
            "draw_prob": 0.29,
            "away_win_prob": 0.29,
            "over_2_5_prob": 0.44,
            "btts_prob": 0.48,
            "home_rating": 1600 + index * 3,
            "away_rating": 1560,
        })
    return pd.DataFrame(rows)


def test_scoreline_metrics_rank_topk_bands_and_outputs(tmp_path):
    rows = _calibration_rows()
    result = evaluate_scoreline_calibration(rows, min_rows=5)
    rankings = scoreline_rankings(rows.head(1))

    assert result["metrics"]["row_count"] == len(rows)
    assert 0 <= result["metrics"]["actual_score_hit_rate"] <= 1
    assert result["metrics"]["top_5_correct_score_hit_rate"] >= result["metrics"]["top_3_correct_score_hit_rate"]
    assert rankings.iloc[0]["actual_score_rank"] >= 1
    assert rankings.iloc[0]["actual_score_probability"] > 0
    assert set(result["team_goal_band_calibration"]["goal_band"]) == {"0", "1", "2", "3+"}
    assert set(result["total_goal_band_calibration"]["total_goal_band"]) == {"0-1", "2", "3", "4+"}

    written = write_scoreline_diagnostics(rows, as_of_date="2026-06-26", output_dir=tmp_path / "calibration", min_rows=5)
    run_dir = Path(written["run_dir"])
    assert (run_dir / "scoreline_diagnostics_summary.md").exists()
    assert (run_dir / "scoreline_metrics.csv").exists()
    assert (run_dir / "scoreline_topk_metrics.csv").exists()
    assert (run_dir / "team_goal_band_calibration.csv").exists()
    assert (run_dir / "total_goal_band_calibration.csv").exists()
    assert (run_dir / "actual_score_rankings.csv").exists()


def test_current_grading_manual_results_miss_types_and_no_fake_fallback(tmp_path):
    projections = pd.DataFrame([{
        "fixture_date": "2026-06-25",
        "team_a": "Curacao",
        "team_b": "Cote d'Ivoire",
        "team_a_xg_final": 0.9,
        "team_b_xg_final": 1.35,
        "projected_total": 2.25,
        "most_likely_score": "0-1",
        "team_a_win_prob": 0.25,
        "draw_prob": 0.29,
        "team_b_win_prob": 0.46,
    }])
    actuals = pd.DataFrame([{
        "fixture_date": "2026-06-25",
        "home_team": "Curacao",
        "away_team": "Cote d'Ivoire",
        "home_goals": 0,
        "away_goals": 2,
        "source_name": "manual_test",
        "result_source_type": "manual_source_supplied",
        "result_source_name": "manual_test",
    }])
    graded = grade_projection_rows(projections, actuals)
    row = graded["graded_matches"].iloc[0]

    assert row["actual_score"] == "0 - 2"
    assert row["top_3_score_hit"] in {True, False}
    assert row["over_2_5_brier_component"] >= 0
    assert row["btts_brier_component"] >= 0
    assert row["miss_type"] in {
        "scoreline_close",
        "total_too_low",
        "clean_sheet_missed",
        "exact_score_hit",
        "winner_wrong",
        "underdog_attack_underestimated",
    }

    projection_path = tmp_path / "projections.csv"
    actual_path = tmp_path / "manual_results.csv"
    projections.to_csv(projection_path, index=False)
    actuals[["fixture_date", "home_team", "away_team", "home_goals", "away_goals", "source_name"]].to_csv(actual_path, index=False)
    manual = load_manual_results(actual_path)
    assert set(manual["result_source_type"]) == {"manual_source_supplied"}

    result = grade_current_projections(
        as_of_date="2026-06-25",
        projection_file=projection_path,
        actual_results=actual_path,
        output_dir=tmp_path / "grading",
    )
    assert result["status"] == "graded"
    assert Path(result["paths"]["graded_matches"]).exists()
    assert result["manifest"]["manual_results_used"] is True
    assert result["manifest"]["guardrails"]["fake_results_used"] is False

    no_results = grade_current_projections(
        as_of_date="2026-06-25",
        projection_file=projection_path,
        source_cache_dir=tmp_path / "empty_cache",
        output_dir=tmp_path / "grading_empty",
    )
    assert no_results["status"] == "no_results_available"
    assert "No allowed cached result source" in no_results["manifest"]["warning"]


def test_tuning_candidate_labels_config_and_preview_are_diagnostic(tmp_path):
    rows = _calibration_rows()
    baseline_metrics = {
        "wdl_log_loss": 1.1,
        "brier_score": 0.22,
        "total_goals_mae": 1.8,
        "over_under_2_5_brier_score": 0.26,
    }
    grid, best = evaluate_tuning_grid(rows, profile="small", baseline_metrics=baseline_metrics)
    assert not grid.empty
    assert {"favorite_xg_spread_multiplier", "underdog_xg_floor", "candidate_label"}.issubset(grid.columns)
    assert set(grid["candidate_label"]).issubset({
        "balanced_improvement",
        "totals_improved_wdl_stable",
        "totals_improved_wdl_hurt",
        "scoreline_spread_improved",
        "overfit_risk",
        "keep_current_baseline",
        "limited_holdout_confidence",
        "insufficient_rows",
    })
    candidate = project_rows_with_candidate(rows, {"baseline_total_goals": 2.65, "rating_diff_to_goal_scale": 900})
    assert candidate["home_xg"].add(candidate["away_xg"]).mean() > 2.3

    config = {
        "config_type": "diagnostic_scoreline_candidate_model_config",
        "production_defaults_changed": False,
        "model_parameters": best.iloc[0][[
            "rating_diff_to_goal_scale",
            "baseline_total_goals",
            "neutral_home_adjustment",
            "draw_dampening",
            "total_goals_adjustment",
            "favorite_xg_spread_multiplier",
            "underdog_xg_floor",
        ]].to_dict(),
    }
    config_path = tmp_path / "candidate_scoreline_model_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    run_dir = tmp_path / "current_international" / "2026-06-26"
    projections = pd.DataFrame([{
        "team_a": "Mexico",
        "team_b": "Canada",
        "team_a_xg_final": 1.25,
        "team_b_xg_final": 1.05,
        "projected_total": 2.3,
        "team_a_win_prob": 0.41,
        "draw_prob": 0.29,
        "team_b_win_prob": 0.30,
        "most_likely_score": "1-1",
        "home_rating": 1700,
        "away_rating": 1600,
    }])
    preview = _write_candidate_projection_preview(run_dir, projections, config_path)
    assert preview["status"] == "written"
    preview_rows = pd.read_csv(preview["paths"]["scoreline_candidate_projection_comparison"])
    assert {"delta_total", "delta_over_2_5_probability", "baseline_top_correct_scores", "candidate_top_correct_scores"}.issubset(preview_rows.columns)
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False


def test_viewer_indexes_grading_outputs_and_uses_exact_score_language(tmp_path):
    grading = grade_current_projections(
        as_of_date="2026-06-25",
        projection_file=tmp_path / "missing.csv",
        output_dir=tmp_path / "outputs" / "grading",
    )
    entries = build_run_index(tmp_path / "outputs")
    assert any(entry["entry_type"] == "current_result_grading" for entry in entries)
    viewer = build_static_viewer(tmp_path / "outputs", tmp_path / "viewer")
    assert viewer["runs_included"] >= 1
    detail = Path(tmp_path / "viewer" / "runs" / f"{grading['manifest']['run_id']}.html")
    assert detail.exists()
    detail_html = detail.read_text(encoding="utf-8")
    assert "current_projection_grading_summary.md" in detail_html

    commands = build_parser()._subparsers._group_actions[0].choices
    assert "grade-current-projections" in commands
    assert "--actual-results" in commands["grade-current-projections"].format_help()
    assert "run-today" in commands


def test_poisson_viewer_language_and_guardrails_registered():
    commands = build_parser()._subparsers._group_actions[0].choices
    assert "validate-v1" in commands
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False

    source_text = Path("src/viewer/static_viewer.py").read_text(encoding="utf-8")
    assert "Most likely exact score" in source_text
    assert "Single highest-probability score cell" in source_text
    assert "Exact scores are naturally low-probability outcomes" in source_text
    assert "current_statsbomb_live_data_used" in Path("src/analysis/scoreline_calibration.py").read_text(encoding="utf-8")


def test_validate_v1_command_still_passes_quickly():
    result = run([sys.executable, "-m", "src.cli", "validate-v1"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

