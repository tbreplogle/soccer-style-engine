from __future__ import annotations

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.operational.daily_runner import run_daily_pipeline
from src.operational.defaults import OPERATIONAL_DEFAULTS, explain_operational_defaults
from src.operational.health_check import run_operational_health_check


ROOT = Path(__file__).resolve().parents[1]


def _raw_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    teams = ["Red FC", "Blue FC", "Green FC", "Yellow FC"]
    rows = []
    for i in range(18):
        rows.append({
            "Date": f"{1 + i:02d}/02/26",
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
            "B365H": 2.0,
            "B365D": 3.2,
            "B365A": 3.6,
            "B365>2.5": 1.9,
            "B365<2.5": 1.9,
        })
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_operational_defaults_contain_phase14_recommendations():
    defaults = OPERATIONAL_DEFAULTS
    assert defaults.club.general_report_profile == "score_projection"
    assert defaults.club.primary_wdl_profile == "winner_probability"
    assert defaults.club.proxy_adjustments_enabled is False
    assert defaults.club.confidence_language == "data_support_context"
    assert defaults.guardrails.no_betting_recommendations is True


def test_daily_runner_local_synthetic_outputs(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv")
    result = run_daily_pipeline(
        "2026-02-20",
        season_code="2526",
        leagues="E0",
        output_root=tmp_path / "runs",
        slate_type="historical",
        max_matches=2,
        skip_download=True,
        run_quick_audit=True,
        raw_input_dir=raw,
        processed_output=tmp_path / "processed.csv",
    )
    run_dir = result["run_dir"]
    assert run_dir.exists()
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "run_summary.md").exists()
    assert (run_dir / "club_slate_report.md").exists()
    assert (run_dir / "club_slate_projections.csv").exists()
    assert (run_dir / "leakage_audit_summary.md").exists()
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["defaults_used"]["club"]["primary_wdl_profile"] == "winner_probability"
    summary = (run_dir / "run_summary.md").read_text(encoding="utf-8")
    assert "Data Support / Risk Context" in summary
    assert "best bet" not in summary.lower()
    assert "pick" not in summary.lower()


def test_failed_download_does_not_fail_when_local_data_exists(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv")

    def fake_download(*args, **kwargs):
        return pd.DataFrame([{"league_code": "E0", "status": "failed", "error": "synthetic failure"}])

    monkeypatch.setattr("src.operational.daily_runner.download_football_data_leagues", fake_download)
    result = run_daily_pipeline(
        "2026-02-20",
        leagues="E0",
        output_root=tmp_path / "runs",
        slate_type="historical",
        max_matches=1,
        skip_download=False,
        raw_input_dir=raw,
        processed_output=tmp_path / "processed.csv",
    )
    assert result["run_dir"].exists()
    assert any("downloads failed" in warning for warning in result["warnings"])


def test_missing_international_data_warns_but_does_not_fail(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv")
    result = run_daily_pipeline(
        "2026-02-20",
        leagues="E0",
        output_root=tmp_path / "runs",
        slate_type="historical",
        max_matches=1,
        skip_download=True,
        include_international=True,
        international_input=tmp_path / "missing.csv",
        raw_input_dir=raw,
        processed_output=tmp_path / "processed.csv",
    )
    assert result["international"] is None
    assert any("International requested" in warning for warning in result["warnings"])


def test_explain_defaults_and_health_check_work():
    explanation = explain_operational_defaults()
    assert "winner_probability" in explanation
    assert "Proxy score adjustments remain disabled" in explanation
    health = run_operational_health_check()
    assert health["health_status"] in {"pass", "warn", "fail"}
    assert any(check["name"] == "cli_commands_registered" for check in health["checks"])


def test_outputs_runs_is_ignored_and_proxy_default_disabled():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "outputs/runs/" in gitignore
    assert "outputs/runs/**" in gitignore
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False


def test_phase15_cli_smoke(tmp_path):
    raw_dir = tmp_path / "raw"
    _raw_csv(raw_dir / "E0_2526.csv")
    output_root = tmp_path / "runs"
    commands = [
        [sys.executable, "-m", "src.cli", "explain-operational-defaults"],
        [sys.executable, "-m", "src.cli", "operational-health-check"],
        [
            sys.executable,
            "-m",
            "src.cli",
            "run-daily-pipeline",
            "--as-of-date",
            "2026-02-20",
            "--season-code",
            "2526",
            "--leagues",
            "E0",
            "--output-root",
            str(output_root),
            "--slate-type",
            "historical",
            "--max-matches",
            "1",
            "--skip-download",
            "--raw-input-dir",
            str(raw_dir),
            "--processed-output",
            str(tmp_path / "processed.csv"),
        ],
    ]
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        assert completed.returncode == 0
    assert (output_root / "2026-02-20" / "run_manifest.json").exists()
