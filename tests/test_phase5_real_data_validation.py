from __future__ import annotations

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration, pytest.mark.real_data_optional]

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.reports.real_data_validation import (
    list_available_real_data,
    run_real_data_validation,
    run_sanity_checks,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_STATSBOMB = ROOT / "data" / "sample" / "statsbomb-open-data"


def test_validation_runs_on_sample_statsbomb_data(tmp_path):
    result = run_real_data_validation(
        SAMPLE_STATSBOMB,
        competition_id=1,
        season_id=1,
        max_matches=5,
        output_dir=tmp_path,
    )

    assert len(result["matches"]) == 1
    assert len(result["style_log"]) == 2
    assert result["report_path"].exists()
    assert "Real Data Validation Summary" in result["report_path"].read_text(encoding="utf-8")


def test_missing_360_is_reported_as_event_only(tmp_path):
    result = run_real_data_validation(
        SAMPLE_STATSBOMB,
        competition_id=1,
        season_id=1,
        output_dir=tmp_path,
    )

    quality = result["quality"].set_index("data_quality_flag")["rows"].to_dict()
    assert quality["event_only"] == 2
    assert "compactness" in result["report"]
    assert "event_only" in result["report"]


def test_sanity_checks_catch_impossible_values():
    bad = pd.DataFrame(
        {
            "match_id": [1],
            "team": ["Only Team"],
            "possession_pct": [120],
            "field_tilt_pct": [-5],
            "xg_for": [0],
            "progressive_passes": [-1],
            "data_quality_flag": ["event_only"],
        }
    )

    warnings = run_sanity_checks(bad, matches_loaded=1)
    assert "Only one or zero teams found." in warnings
    assert "possession_pct contains values outside 0-100." in warnings
    assert "field_tilt_pct contains values outside 0-100." in warnings
    assert "xG is missing or zero for every team-match row." in warnings
    assert "progressive_passes contains negative counts." in warnings
    assert "Team-match row count 1 does not equal 2 x matches loaded (2)." in warnings


def test_raw_data_is_not_tracked_except_gitkeep():
    tracked = subprocess.run(
        ["git", "ls-files", "data/raw"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    assert set(tracked).issubset({"data/raw/.gitkeep", "data/raw/football-data/.gitkeep"})


def test_list_available_real_data_sample():
    available = list_available_real_data(SAMPLE_STATSBOMB)

    assert not available.empty
    assert int(available.iloc[0]["competition_id"]) == 1
    assert int(available.iloc[0]["season_id"]) == 1


def test_validate_real_data_cli_smoke_on_sample(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "validate-real-data",
            "--statsbomb-root",
            str(SAMPLE_STATSBOMB),
            "--competition-id",
            "1",
            "--season-id",
            "1",
            "--max-matches",
            "5",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Real data validation complete" in completed.stdout
    assert (tmp_path / "real_data_validation_summary.md").exists()
