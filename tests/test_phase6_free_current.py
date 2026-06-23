from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.data_ingestion.football_data_current import normalize_current_football_data, normalize_current_inputs
from src.features.free_style_proxies import build_current_team_ratings, build_free_style_proxies
from src.models.current_backtest import run_current_backtest
from src.models.current_score_projection import project_current_match, proxy_adjustments_are_capped


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FOLDER = ROOT / "data" / "sample" / "football-data"
SAMPLE_CSV = SAMPLE_FOLDER / "sample_current_results.csv"


def test_current_loader_normalizes_sample_csv():
    normalized = normalize_current_inputs(SAMPLE_FOLDER, league="SYN", season="2025-2026")

    assert len(normalized) == 24
    assert {"home_shots", "away_shots_on_target", "home_odds_close", "data_quality_flags"}.issubset(normalized.columns)
    assert normalized["data_quality_flags"].eq("complete_basic_match_stats").all()


def test_missing_optional_columns_become_null_and_flags():
    raw = pd.DataFrame(
        {
            "Date": ["01/01/26"],
            "HomeTeam": ["A"],
            "AwayTeam": ["B"],
            "FTHG": [1],
            "FTAG": [0],
            "FTR": ["H"],
        }
    )
    normalized = normalize_current_football_data(raw, league="SYN", season="2025-2026")

    assert pd.isna(normalized.loc[0, "home_shots"])
    assert "missing_shots" in normalized.loc[0, "data_quality_flags"]
    assert "missing_odds" in normalized.loc[0, "data_quality_flags"]


def test_current_team_ratings_use_only_prior_matches():
    normalized = normalize_current_inputs(SAMPLE_FOLDER, league="SYN", season="2025-2026")
    ratings = build_current_team_ratings(normalized, "2026-02-01").set_index("team")

    assert int(ratings.loc["Red FC", "matches_played"]) == 7
    assert ratings.loc["Red FC", "goals_for_per_match"] > ratings.loc["Blue FC", "goals_for_per_match"]


def test_free_style_proxies_include_proxy_fields():
    normalized = normalize_current_inputs(SAMPLE_FOLDER, league="SYN", season="2025-2026")
    proxies = build_free_style_proxies(normalized, "2026-02-01")
    red = proxies.set_index("team").loc["Red FC"]

    assert red["data_mode"] == "free_proxy_style"
    assert red["control_proxy"] >= 0
    assert "data_mode=free_proxy_style" in red["control_proxy_evidence"]


def test_proxy_reliability_drops_on_small_sample():
    normalized = normalize_current_inputs(SAMPLE_FOLDER, league="SYN", season="2025-2026")
    proxies = build_free_style_proxies(normalized, "2026-01-10")

    assert proxies["control_proxy_reliability"].eq("Low").all()


def test_current_score_projection_probabilities_and_data_mode():
    normalized = normalize_current_inputs(SAMPLE_FOLDER, league="SYN", season="2025-2026")
    projection = project_current_match(normalized, "Red FC", "Blue FC", "2026-02-01")
    row = projection.iloc[0]

    assert abs((row["home_win_prob"] + row["draw_prob"] + row["away_win_prob"]) - 1.0) < 1e-6
    assert abs((row["over_2_5_prob"] + row["under_2_5_prob"]) - 1.0) < 1e-6
    assert row["data_mode"] == "free_proxy_style"
    assert "tracking" in row["warnings"]


def test_style_proxy_adjustments_are_capped():
    normalized = normalize_current_inputs(SAMPLE_FOLDER, league="SYN", season="2025-2026")

    assert proxy_adjustments_are_capped(normalized, "Red FC", "Blue FC", "2026-02-01")


def test_current_backtest_runs_without_leakage(tmp_path):
    normalized = normalize_current_inputs(SAMPLE_FOLDER, league="SYN", season="2025-2026")
    result = run_current_backtest(normalized, "2026-01-15", "2026-02-15", output_dir=tmp_path)

    assert not result["results"].empty
    assert (tmp_path / "free_current_backtest_results.csv").exists()
    assert "Proxy lift" in result["summary"]


def test_current_cli_smoke_normalize_project_backtest(tmp_path):
    normalized_path = tmp_path / "current_match_results.csv"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "normalize-football-data",
            "--input",
            str(SAMPLE_FOLDER),
            "--output",
            str(normalized_path),
            "--league",
            "SYN",
            "--season",
            "2025-2026",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    project = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "project-current",
            "--input",
            str(normalized_path),
            "--home",
            "Red FC",
            "--away",
            "Blue FC",
            "--as-of-date",
            "2026-02-01",
            "--output",
            str(tmp_path / "projection.csv"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    backtest = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "backtest-current",
            "--input",
            str(normalized_path),
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

    assert normalized_path.exists()
    assert "free_proxy_style" in project.stdout
    assert "Free Current Backtest Summary" in backtest.stdout
