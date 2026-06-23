from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.data_ingestion.football_data_current import normalize_current_inputs
from src.models.current_score_projection import project_current_match, resolve_projection_profile_baseline
from src.models.market_comparison import calculate_implied_probs_from_match_odds, compare_model_to_market, summarize_market_gap
from src.models.projection_confidence import score_projection_confidence
from src.models.projection_profile_diagnostics import run_projection_profile_diagnostics


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FOLDER = ROOT / "data" / "sample" / "football-data"


def _sample() -> pd.DataFrame:
    return normalize_current_inputs(SAMPLE_FOLDER, league="SYN", season="2025-2026")


def test_projection_profile_selection_and_baseline_override():
    assert resolve_projection_profile_baseline("winner_probability", None, True, True) == ("winner_probability", "market")
    assert resolve_projection_profile_baseline("total_goals", None, False, True) == ("total_goals", "totals_market")
    assert resolve_projection_profile_baseline("winner_probability", "goals", True, True) == ("winner_probability", "goals")


def test_confidence_score_is_bounded_and_low_for_small_samples():
    confidence = score_projection_confidence(
        _sample(),
        {"baseline_mode": "goals", "home_prior_matches": 2, "away_prior_matches": 4},
        {"goals": {"home_xg_base": 1.2, "away_xg_base": 1.0, "available": True}},
        {"market_home_prob": None, "market_draw_prob": None, "market_away_prob": None, "largest_gap_value": None},
        proxy_adjustments_enabled=False,
        projection_profile="score_projection",
    )
    assert 0 <= confidence["confidence_score"] <= 100
    assert confidence["confidence_label"] == "Low"


def test_missing_odds_reduces_market_confidence():
    base = {"baseline_mode": "market", "home_prior_matches": 8, "away_prior_matches": 8}
    baselines = {"goals": {"home_xg_base": 1.2, "away_xg_base": 1.0, "available": True}}
    missing = score_projection_confidence(_sample(), base, baselines, {"market_home_prob": None, "market_draw_prob": None, "market_away_prob": None}, False, "market_anchored")
    present = score_projection_confidence(_sample(), base, baselines, {"market_home_prob": 0.4, "market_draw_prob": 0.3, "market_away_prob": 0.3, "largest_gap_value": 0.02}, False, "market_anchored")
    assert present["confidence_score"] > missing["confidence_score"]


def test_model_only_excludes_market_and_market_anchored_includes_it():
    data = _sample()
    model_only = project_current_match(data, "Red FC", "Blue FC", "2026-02-01", projection_profile="model_only").iloc[0]
    anchored = project_current_match(data, "Red FC", "Blue FC", "2026-02-01", projection_profile="market_anchored").iloc[0]
    assert model_only["market_influence_level"] == "None"
    assert "No usable 1X2 market odds" in model_only["market_gap_summary"]
    assert anchored["market_influence_level"] in {"Medium", "High"}


def test_market_comparison_probs_and_summary_are_not_recommendations():
    probs = calculate_implied_probs_from_match_odds(2.0, 4.0, 4.0)
    assert abs(sum(v for v in probs.values() if v is not None) - 1.0) < 1e-9
    comparison = compare_model_to_market({"home_win_prob": 0.5, "draw_prob": 0.25, "away_win_prob": 0.25, "over_2_5_prob": 0.52}, {"home_odds_close": 2.2, "draw_odds_close": 3.4, "away_odds_close": 3.2})
    summary = summarize_market_gap(comparison)
    assert "recommendation" in summary
    assert "edge pick" not in summary.lower()


def test_projection_output_contains_phase10_fields_and_proxy_off():
    row = project_current_match(_sample(), "Red FC", "Blue FC", "2026-02-01", projection_profile="score_projection").iloc[0]
    required = {
        "projection_profile",
        "baseline_mode_used",
        "market_influence_level",
        "confidence_score",
        "confidence_label",
        "confidence_reasons",
        "risk_flags",
        "disagreement_flags",
        "model_market_gap_summary",
    }
    assert required.issubset(row.index)
    assert row["home_xg_proxy_adjustment"] == 0
    assert row["away_xg_proxy_adjustment"] == 0
    assert pd.isna(row["betting_recommendation"])


def test_projection_profile_diagnostics_runs_on_sample(tmp_path):
    result = run_projection_profile_diagnostics(_sample(), "2026-01-15", "2026-02-15", output_dir=tmp_path)
    assert not result["results"].empty
    assert "confidence_bucket_summary" in result["results"].columns
    assert (tmp_path / "projection_profile_diagnostics_results.csv").exists()


def test_project_current_projection_profile_cli_smoke(tmp_path):
    current_path = tmp_path / "current.csv"
    normalize_current_inputs(SAMPLE_FOLDER, output_path=current_path, league="SYN", season="2025-2026")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "project-current",
            "--input",
            str(current_path),
            "--home",
            "Red FC",
            "--away",
            "Blue FC",
            "--as-of-date",
            "2026-02-01",
            "--projection-profile",
            "winner_probability",
            "--output",
            str(tmp_path / "projection.csv"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "winner_probability" in completed.stdout


def test_diagnose_projection_profiles_cli_smoke(tmp_path):
    current_path = tmp_path / "current.csv"
    normalize_current_inputs(SAMPLE_FOLDER, output_path=current_path, league="SYN", season="2025-2026")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "diagnose-projection-profiles",
            "--input",
            str(current_path),
            "--start-date",
            "2026-01-15",
            "--end-date",
            "2026-02-15",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Projection Profile Diagnostics Summary" in completed.stdout


def test_profile_diagnostics_enforces_no_future_leakage(tmp_path):
    gated = run_projection_profile_diagnostics(_sample(), "2026-01-15", "2026-01-20", min_matches=6, output_dir=tmp_path / "gated")
    loose = run_projection_profile_diagnostics(_sample(), "2026-01-15", "2026-01-20", min_matches=1, output_dir=tmp_path / "loose")
    assert gated["results"]["matches"].sum() == 0
    assert loose["results"]["matches"].sum() > 0

