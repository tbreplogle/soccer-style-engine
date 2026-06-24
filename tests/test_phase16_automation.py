from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.operational.currentness import check_data_currentness
from src.operational.daily_runner import run_daily_pipeline
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.operational.run_log import write_run_log
from src.operational.season_sanity import check_season_sanity


ROOT = Path(__file__).resolve().parents[1]


def _raw_csv(path: Path, start: str = "01/02/26", rows: int = 10, include_odds: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    base = pd.to_datetime(start, dayfirst=True)
    teams = ["Red FC", "Blue FC", "Green FC", "Yellow FC"]
    records = []
    for i in range(rows):
        row = {
            "Date": (base + pd.Timedelta(days=i)).strftime("%d/%m/%y"),
            "HomeTeam": teams[i % 4],
            "AwayTeam": teams[(i + 1) % 4],
            "FTHG": i % 4,
            "FTAG": (i + 1) % 3,
            "FTR": "H" if (i % 4) > ((i + 1) % 3) else "A" if (i % 4) < ((i + 1) % 3) else "D",
            "HS": 10 + i % 4,
            "AS": 8 + i % 4,
            "HST": 4 + i % 3,
            "AST": 3 + i % 3,
            "HC": 5,
            "AC": 4,
        }
        if include_odds:
            row.update({"B365H": 2.0, "B365D": 3.2, "B365A": 3.6})
        records.append(row)
    pd.DataFrame(records).to_csv(path, index=False)
    return path


def test_currentness_detects_missing_raw_data(tmp_path):
    result = check_data_currentness(tmp_path / "raw", tmp_path / "processed.csv", "2026-05-25", "2526", "E0,E1")
    assert result["currentness_status"] == "missing"
    assert set(result["leagues_missing"]) == {"E0", "E1"}


def test_currentness_detects_missing_processed_data(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", start="01/05/26")
    result = check_data_currentness(raw, tmp_path / "missing.csv", "2026-05-12", "2526", "E0")
    assert result["processed_data_state"] == "missing"
    assert result["currentness_status"] in {"current", "probably_current"}
    assert any("Processed data is missing" in warning for warning in result["warnings"])


def test_currentness_detects_stale_and_allows_offseason_historical(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", start="01/08/25")
    stale = check_data_currentness(raw, None, "2026-02-01", "2526", "E0")
    assert stale["currentness_status"] == "stale"
    offseason = check_data_currentness(raw, None, "2026-07-15", "2526", "E0", historical_mode=True)
    assert offseason["currentness_status"] == "probably_current"
    assert any("offseason" in warning.lower() or "historical" in warning.lower() for warning in offseason["warnings"])


def test_currentness_identifies_missing_league(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", start="01/05/26")
    result = check_data_currentness(raw, None, "2026-05-12", "2526", "E0,E1")
    assert result["currentness_status"] == "missing"
    assert result["leagues_missing"] == ["E1"]


def test_season_sanity_passes_and_warns():
    ok = check_season_sanity("2526", "2026-05-25")
    warn = check_season_sanity("2526", "2027-05-25")
    assert ok["season_sanity_status"] == "ok"
    assert warn["season_sanity_status"] == "warning"
    assert warn["warnings"]


def test_run_log_writes_csv_and_jsonl(tmp_path):
    paths = write_run_log({
        "run_id": "x",
        "run_date": "2026-05-25",
        "generated_at": "2026-05-25T00:00:00+00:00",
        "status": "success",
        "currentness_status": "current",
        "season_sanity_status": "ok",
        "leagues": "E0",
        "row_count": 10,
        "slate_type": "historical_validation_slate",
        "outputs_written": 2,
        "warnings_count": 0,
        "error_message": "",
        "duration_seconds": 1.2,
    }, output_dir=tmp_path)
    assert paths["csv_path"].exists()
    assert paths["jsonl_path"].exists()
    with paths["csv_path"].open(encoding="utf-8") as handle:
        assert list(csv.DictReader(handle))[0]["status"] == "success"
    assert json.loads(paths["jsonl_path"].read_text(encoding="utf-8").splitlines()[0])["currentness_status"] == "current"


def test_daily_runner_warn_policy_and_report_headers_for_stale_data(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", start="01/08/25", rows=12)
    result = run_daily_pipeline(
        "2026-02-01",
        season_code="2526",
        leagues="E0",
        output_root=tmp_path / "runs",
        slate_type="historical",
        max_matches=1,
        skip_download=True,
        currentness_policy="warn",
        raw_input_dir=raw,
        processed_output=tmp_path / "processed.csv",
        run_log_dir=tmp_path / "logs",
    )
    assert result["status"] == "success_with_warnings"
    assert result["currentness"]["currentness_status"] == "stale"
    summary = Path(result["summary_path"]).read_text(encoding="utf-8")
    assert "Data currentness status: `stale`" in summary
    assert "Do not trust this slate" in summary
    assert "best bet" not in summary.lower()
    assert "betting pick" not in summary.lower()


def test_daily_runner_fails_under_fail_on_stale_policy(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", start="01/08/25", rows=12)
    result = run_daily_pipeline(
        "2026-02-01",
        season_code="2526",
        leagues="E0",
        output_root=tmp_path / "runs",
        slate_type="historical",
        max_matches=1,
        skip_download=True,
        currentness_policy="fail-on-stale",
        raw_input_dir=raw,
        processed_output=tmp_path / "processed.csv",
        run_log_dir=tmp_path / "logs",
    )
    assert result["status"] == "failed_unsafe_data"
    assert Path(result["manifest_path"]).exists()
    assert Path(result["run_log_paths"]["csv_path"]).exists()


def test_download_failure_does_not_fail_if_local_data_usable(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", start="01/05/26", rows=12)

    def fail_download(*args, **kwargs):
        raise OSError("synthetic network failure")

    monkeypatch.setattr("src.operational.daily_runner.download_football_data_leagues", fail_download)
    result = run_daily_pipeline(
        "2026-05-12",
        season_code="2526",
        leagues="E0",
        output_root=tmp_path / "runs",
        slate_type="historical",
        max_matches=1,
        skip_download=False,
        currentness_policy="warn",
        raw_input_dir=raw,
        processed_output=tmp_path / "processed.csv",
        run_log_dir=tmp_path / "logs",
    )
    assert result["status"] == "success_with_warnings"
    assert any("download failed" in warning.lower() for warning in result["warnings"])


def test_phase16_cli_smoke(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv", start="01/05/26", rows=12)
    processed = tmp_path / "processed.csv"
    commands = [
        [sys.executable, "-m", "src.cli", "check-season-sanity", "--season-code", "2526", "--as-of-date", "2026-05-25"],
        [sys.executable, "-m", "src.cli", "check-data-currentness", "--raw-dir", str(raw), "--processed", str(processed), "--as-of-date", "2026-05-12", "--season-code", "2526", "--leagues", "E0"],
        [sys.executable, "-m", "src.cli", "operational-health-check"],
        [
            sys.executable,
            "-m",
            "src.cli",
            "run-daily-pipeline",
            "--as-of-date",
            "2026-05-12",
            "--season-code",
            "2526",
            "--leagues",
            "E0",
            "--output-root",
            str(tmp_path / "runs"),
            "--slate-type",
            "historical",
            "--max-matches",
            "1",
            "--skip-download",
            "--currentness-policy",
            "warn",
            "--raw-input-dir",
            str(raw),
            "--processed-output",
            str(processed),
        ],
    ]
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        assert completed.returncode == 0


def test_phase16_scripts_ignored_outputs_and_proxy_default():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "outputs/run_logs/" in gitignore
    assert "outputs/runs/" in gitignore
    assert (ROOT / "scripts" / "run_daily_pipeline.ps1").exists()
    assert (ROOT / "scripts" / "task_scheduler_example.ps1").exists()
    assert (ROOT / "scripts" / "run_daily_pipeline.bat").exists()
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
