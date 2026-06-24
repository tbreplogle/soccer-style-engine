from __future__ import annotations

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.data_ingestion.football_data_current import normalize_current_inputs
from src.models.current_score_projection import project_current_match
from src.models.proxy_diagnostics import REQUIRED_METRICS, recommend_proxy_policy, run_proxy_diagnostics


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FOLDER = ROOT / "data" / "sample" / "football-data"


def _sample_current() -> pd.DataFrame:
    return normalize_current_inputs(SAMPLE_FOLDER, league="SYN", season="2025-2026")


def test_diagnostics_runs_on_sample_current_data(tmp_path):
    result = run_proxy_diagnostics(
        _sample_current(),
        "2026-01-15",
        "2026-02-15",
        caps=[0, 0.03, 0.05],
        output_dir=tmp_path,
    )

    assert not result["results"].empty
    assert result["summary_path"].exists()
    assert result["results_path"].exists()
    assert result["recommendation"] in {
        "disable_proxy_adjustments",
        "use_proxy_adjustments_low_cap",
        "use_proxy_adjustments_context_only",
        "needs_more_data",
    }


def test_baseline_cap_zero_equals_baseline_only():
    result = run_proxy_diagnostics(
        _sample_current(),
        "2026-01-15",
        "2026-02-15",
        caps=[0],
    )["results"]
    custom = result[result["window"].eq("custom")]
    baseline = custom[custom["config_name"].eq("baseline_only")].iloc[0]
    all_zero = custom[custom["config_name"].eq("all_proxies_cap_0")].iloc[0]

    assert baseline["total_goals_mae"] == all_zero["total_goals_mae"]
    assert all_zero["lift_vs_baseline_total_mae"] == 0


def test_proxy_cap_values_are_respected():
    result = run_proxy_diagnostics(
        _sample_current(),
        "2026-01-15",
        "2026-02-15",
        caps=[0, 0.03, 0.05],
    )["results"]

    assert set(result["cap"]).issubset({0.0, 0.03, 0.05})


def test_recommendation_outputs_expected_labels():
    small = pd.DataFrame({"window": ["custom"], "config_name": ["baseline_only"], "matches": [3], "lift_vs_baseline_total_mae": [0.0]})
    negative = pd.DataFrame({
        "window": ["custom", "month_a", "month_b"],
        "config_name": ["all", "all", "all"],
        "matches": [100, 50, 50],
        "lift_vs_baseline_total_mae": [-0.01, 0.0, -0.02],
    })
    low_cap = pd.DataFrame({
        "window": ["custom", "month_a", "month_b"],
        "config_name": ["only_control", "only_control", "only_control"],
        "enabled_proxy_groups": ["control_proxy", "control_proxy", "control_proxy"],
        "cap": [0.03, 0.03, 0.03],
        "matches": [100, 50, 50],
        "lift_vs_baseline_total_mae": [0.05, 0.03, 0.04],
    })
    unstable = pd.DataFrame({
        "window": ["custom", "month_a", "month_b"],
        "config_name": ["all", "all", "all"],
        "enabled_proxy_groups": ["control_proxy,tempo_proxy,chaos_proxy"] * 3,
        "cap": [0.08, 0.08, 0.08],
        "matches": [100, 50, 50],
        "lift_vs_baseline_total_mae": [0.05, -0.02, 0.04],
    })

    assert recommend_proxy_policy(small, min_matches=25) == "needs_more_data"
    assert recommend_proxy_policy(negative, min_matches=25) == "disable_proxy_adjustments"
    assert recommend_proxy_policy(low_cap, min_matches=25) == "use_proxy_adjustments_low_cap"
    assert recommend_proxy_policy(unstable, min_matches=25) == "use_proxy_adjustments_context_only"


def test_diagnostics_output_includes_required_metrics():
    result = run_proxy_diagnostics(
        _sample_current(),
        "2026-01-15",
        "2026-02-15",
        caps=[0, 0.03],
    )["results"]

    for metric in REQUIRED_METRICS:
        assert metric in result.columns


def test_project_current_disables_adjustments_by_default():
    projection = project_current_match(_sample_current(), "Red FC", "Blue FC", "2026-02-01").iloc[0]

    assert projection["home_xg_proxy_adjustment"] == 0
    assert projection["away_xg_proxy_adjustment"] == 0
    assert "disabled by default" in projection["warnings"]


def test_diagnose_proxies_cli_smoke(tmp_path):
    current_path = tmp_path / "current.csv"
    normalize_current_inputs(SAMPLE_FOLDER, output_path=current_path, league="SYN", season="2025-2026")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "diagnose-proxies",
            "--input",
            str(current_path),
            "--start-date",
            "2026-01-15",
            "--end-date",
            "2026-02-15",
            "--caps",
            "0,0.03",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Proxy Diagnostics Summary" in completed.stdout
    assert (tmp_path / "proxy_diagnostics_results.csv").exists()
    assert (tmp_path / "proxy_diagnostics_summary.md").exists()
