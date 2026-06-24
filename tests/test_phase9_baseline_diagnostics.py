from __future__ import annotations

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.data_ingestion.football_data_current import normalize_current_inputs
from src.models.baseline_diagnostics import BASELINE_REQUIRED_METRICS, run_baseline_diagnostics
from src.models.current_score_projection import project_current_match
from src.models.market_baseline import (
    blend_baseline_xg,
    convert_decimal_odds_to_implied_probs,
    estimate_current_baseline_xg,
    estimate_market_home_away_strength,
    estimate_market_total_pressure_from_ou25,
    remove_vig_basic,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FOLDER = ROOT / "data" / "sample" / "football-data"


def _sample() -> pd.DataFrame:
    return normalize_current_inputs(SAMPLE_FOLDER, league="SYN", season="2025-2026")


def test_decimal_odds_to_implied_probabilities():
    probs = convert_decimal_odds_to_implied_probs(2.0, 4.0, None)
    assert probs == [0.5, 0.25, None]


def test_remove_vig_sums_to_one():
    probs = remove_vig_basic([0.5, 0.3, 0.25])
    assert abs(sum(p for p in probs if p is not None) - 1.0) < 1e-9


def test_market_helper_handles_missing_odds():
    strength = estimate_market_home_away_strength(None, 3.5, 2.2)
    total = estimate_market_total_pressure_from_ou25(None, 1.9)
    assert strength["home_strength_share"] is None
    assert total["total_pressure"] is None


def test_goals_baseline_uses_prior_matches_only():
    early = estimate_current_baseline_xg(_sample(), "Red FC", "Blue FC", "2026-01-10", baseline_mode="goals")
    later = estimate_current_baseline_xg(_sample(), "Red FC", "Blue FC", "2026-02-01", baseline_mode="goals")
    assert early["home_prior_matches"] < later["home_prior_matches"]
    assert early["home_xg_base"] != later["home_xg_base"]


def test_shots_baseline_falls_back_when_missing_shots():
    data = _sample().drop(columns=["home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target"])
    baseline = estimate_current_baseline_xg(data, "Red FC", "Blue FC", "2026-02-01", baseline_mode="shots")
    assert baseline["available"] is False
    assert baseline["fallback"] == "goals"


def test_totals_market_baseline_handles_missing_ou_odds():
    data = _sample().drop(columns=["over_2_5_odds_close", "under_2_5_odds_close"])
    baseline = estimate_current_baseline_xg(data, "Red FC", "Blue FC", "2026-02-01", baseline_mode="totals_market")
    assert baseline["available"] is False
    assert baseline["fallback"] == "goals"


def test_blended_baseline_falls_back_without_market_columns():
    data = _sample().drop(columns=["home_odds_close", "draw_odds_close", "away_odds_close", "over_2_5_odds_close", "under_2_5_odds_close"])
    baseline = estimate_current_baseline_xg(data, "Red FC", "Blue FC", "2026-02-01", baseline_mode="blended")
    assert baseline["baseline_mode"] == "blended"
    assert baseline["home_xg_base"] > 0


def test_current_projection_supports_baseline_modes_and_proxy_off():
    for mode in ["goals", "shots", "market", "totals_market", "blended"]:
        row = project_current_match(_sample(), "Red FC", "Blue FC", "2026-02-01", baseline_mode=mode).iloc[0]
        assert row["baseline_mode"] == mode
        assert row["home_xg_proxy_adjustment"] == 0
        assert row["away_xg_proxy_adjustment"] == 0


def test_baseline_diagnostics_runs_on_sample(tmp_path):
    result = run_baseline_diagnostics(_sample(), "2026-01-15", "2026-02-15", output_dir=tmp_path)
    assert not result["results"].empty
    for metric in BASELINE_REQUIRED_METRICS:
        assert metric in result["results"].columns
    assert (tmp_path / "baseline_diagnostics_results.csv").exists()


def test_baseline_diagnostics_enforces_prior_match_gate(tmp_path):
    gated = run_baseline_diagnostics(_sample(), "2026-01-15", "2026-01-20", min_matches=6, output_dir=tmp_path / "gated")
    loose = run_baseline_diagnostics(_sample(), "2026-01-15", "2026-01-20", min_matches=1, output_dir=tmp_path / "loose")
    assert gated["results"]["matches"].sum() == 0
    assert loose["results"]["matches"].sum() > 0


def test_diagnose_baselines_cli_smoke(tmp_path):
    current_path = tmp_path / "current.csv"
    normalize_current_inputs(SAMPLE_FOLDER, output_path=current_path, league="SYN", season="2025-2026")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "diagnose-baselines",
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
    assert "Baseline Diagnostics Summary" in completed.stdout
    assert (tmp_path / "baseline_diagnostics_summary.md").exists()
