from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.operational.currentness import check_data_currentness
from src.operational.daily_runner import run_daily_pipeline
from src.operational.defaults import OPERATIONAL_DEFAULTS


ROOT = Path(__file__).resolve().parents[1]


def _raw_csv(path: Path, start: str = "01/05/26", rows: int = 4, include_future: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    base = pd.to_datetime(start, dayfirst=True)
    teams = ["Red FC", "Blue FC", "Green FC", "Yellow FC"]
    records = []
    for i in range(rows):
        records.append({
            "Date": (base + pd.Timedelta(days=i)).strftime("%d/%m/%y"),
            "HomeTeam": teams[i % 4],
            "AwayTeam": teams[(i + 1) % 4],
            "FTHG": i % 4,
            "FTAG": (i + 1) % 3,
            "FTR": "H",
            "HS": 10,
            "AS": 8,
            "HST": 4,
            "AST": 3,
            "HC": 5,
            "AC": 4,
            "B365H": 2.0,
            "B365D": 3.2,
            "B365A": 3.6,
        })
    if include_future:
        records.append({
            "Date": (base + pd.Timedelta(days=rows + 10)).strftime("%d/%m/%y"),
            "HomeTeam": "Red FC",
            "AwayTeam": "Green FC",
            "FTHG": "",
            "FTAG": "",
            "FTR": "",
            "HS": "",
            "AS": "",
            "HST": "",
            "AST": "",
            "HC": "",
            "AC": "",
            "B365H": 2.0,
            "B365D": 3.2,
            "B365A": 3.6,
        })
    pd.DataFrame(records).to_csv(path, index=False)
    return path


def test_completed_league_not_marked_stale(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E1_2526.csv", start="01/05/26", rows=4)
    result = check_data_currentness(raw, None, "2026-05-25", "2526", "E1", expected_match_counts={"E1": (4,)})
    assert result["league_statuses"]["E1"] == "season_completed"
    assert result["overall_currentness_status"] == "season_completed"
    assert result["leagues_stale"] == []


def test_e1_completed_earlier_than_epl_does_not_make_overall_stale(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E1_2526.csv", start="01/05/26", rows=4)
    _raw_csv(raw / "E0_2526.csv", start="20/05/26", rows=4)
    result = check_data_currentness(
        raw,
        None,
        "2026-05-25",
        "2526",
        "E0,E1",
        expected_match_counts={"E0": (4,), "E1": (4,)},
    )
    assert result["league_statuses"]["E1"] == "season_completed"
    assert result["overall_currentness_status"] == "season_completed"


def test_active_league_with_old_latest_completed_is_stale(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", start="01/08/25", rows=3, include_future=True)
    result = check_data_currentness(raw, None, "2026-02-01", "2526", "E0", slate_type="future", expected_match_counts={"E0": (4,)})
    assert result["league_statuses"]["E0"] == "stale"
    assert result["overall_currentness_status"] == "stale"


def test_all_leagues_completed_after_season_end_is_completed_or_historical_ok(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", start="01/05/26", rows=4)
    result = check_data_currentness(raw, None, "2026-07-15", "2526", "E0", historical_mode=True, expected_match_counts={"E0": (4,)})
    assert result["overall_currentness_status"] in {"season_completed", "historical_ok"}


def test_processed_freshness_detects_older_than_raw_and_fresh_after_runner(tmp_path):
    raw = tmp_path / "raw"
    raw_file = _raw_csv(raw / "E0_2526.csv", rows=12)
    processed = tmp_path / "processed.csv"
    processed.write_text("date,league,home_team,away_team,home_goals,away_goals\n", encoding="utf-8")
    os.utime(processed, (raw_file.stat().st_mtime - 100, raw_file.stat().st_mtime - 100))
    old = check_data_currentness(raw, processed, "2026-05-12", "2526", "E0")
    assert old["processed_freshness_status"] == "older_than_raw"
    run = run_daily_pipeline(
        "2026-05-12",
        season_code="2526",
        leagues="E0",
        output_root=tmp_path / "runs",
        slate_type="historical",
        max_matches=1,
        skip_download=True,
        skip_profile_comparison=True,
        raw_input_dir=raw,
        processed_output=processed,
        run_log_dir=tmp_path / "logs",
    )
    assert run["manifest"]["processed_freshness"]["processed_freshness_status"] == "fresh"


def test_historical_stale_warns_but_future_strict_blocks(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", start="01/08/25", rows=12)
    hist = run_daily_pipeline(
        "2026-02-01",
        season_code="2526",
        leagues="E0",
        output_root=tmp_path / "hist",
        slate_type="historical",
        max_matches=1,
        skip_download=True,
        currentness_policy="fail-on-stale",
        skip_profile_comparison=True,
        raw_input_dir=raw,
        processed_output=tmp_path / "hist_processed.csv",
        run_log_dir=tmp_path / "logs",
    )
    assert hist["status"] == "success_with_warnings"
    future = run_daily_pipeline(
        "2026-02-01",
        season_code="2526",
        leagues="E0",
        output_root=tmp_path / "future",
        slate_type="future",
        max_matches=1,
        skip_download=True,
        currentness_policy="fail-on-stale",
        skip_profile_comparison=True,
        raw_input_dir=raw,
        processed_output=tmp_path / "future_processed.csv",
        run_log_dir=tmp_path / "logs",
    )
    assert future["status"] == "failed_unsafe_data"


def test_daily_runner_skip_profile_comparison_custom_profiles_and_timing(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", rows=12)
    result = run_daily_pipeline(
        "2026-05-12",
        season_code="2526",
        leagues="E0",
        output_root=tmp_path / "runs",
        slate_type="historical",
        max_matches=1,
        skip_download=True,
        skip_profile_comparison=True,
        profiles="score_projection,winner_probability",
        raw_input_dir=raw,
        processed_output=tmp_path / "processed.csv",
        run_log_dir=tmp_path / "logs",
    )
    assert result["comparison"] is None
    assert result["manifest"]["profiles_run"] == ["score_projection", "winner_probability"]
    assert "download_seconds" in result["manifest"]["timing"]
    assert "normalization_seconds" in result["manifest"]["timing"]
    assert "slate_seconds" in result["manifest"]["timing"]
    assert "total_duration_seconds" in result["manifest"]["timing"]
    log = (tmp_path / "logs" / "daily_pipeline_log.csv").read_text(encoding="utf-8")
    assert "download_seconds" in log
    summary = Path(result["summary_path"]).read_text(encoding="utf-8")
    assert "## Warning Groups" in summary


def test_explain_currentness_and_check_cli_outputs_league_table(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", rows=4)
    explain = subprocess.run([sys.executable, "-m", "src.cli", "explain-currentness"], cwd=ROOT, capture_output=True, text=True, check=True)
    check = subprocess.run([
        sys.executable,
        "-m",
        "src.cli",
        "check-data-currentness",
        "--raw-dir",
        str(raw),
        "--processed",
        str(tmp_path / "processed.csv"),
        "--as-of-date",
        "2026-05-12",
        "--season-code",
        "2526",
        "--leagues",
        "E0",
        "--slate-type",
        "historical",
    ], cwd=ROOT, capture_output=True, text=True, check=True)
    assert "Completed leagues are not stale" in explain.stdout
    assert "| league | status | completed | expected | pct | latest_completed | finished |" in check.stdout


def test_no_betting_language_and_proxy_disabled_in_runner_output(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", rows=12)
    result = run_daily_pipeline(
        "2026-05-12",
        season_code="2526",
        leagues="E0",
        output_root=tmp_path / "runs",
        slate_type="historical",
        max_matches=1,
        skip_download=True,
        skip_profile_comparison=True,
        raw_input_dir=raw,
        processed_output=tmp_path / "processed.csv",
        run_log_dir=tmp_path / "logs",
    )
    text = Path(result["summary_path"]).read_text(encoding="utf-8").lower()
    assert "best bet" not in text
    assert "betting pick" not in text
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
