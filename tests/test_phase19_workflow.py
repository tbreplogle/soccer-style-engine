from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import src.cli as cli
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.operational.health_check import run_operational_health_check
from src.viewer.static_viewer import build_static_viewer


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.quick


def _minimal_run(run_dir: Path, run_date: str, generated_at: str, warnings: list[str] | None = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    warnings = warnings or []
    (run_dir / "run_manifest.json").write_text(
        """
{
  "run_id": "%s",
  "run_date": "%s",
  "generated_at": "%s",
  "status": "success_with_warnings",
  "currentness_status": "season_completed",
  "season_sanity_status": "ok",
  "leagues": ["E0"],
  "normalized_row_counts": {"total_rows": 4},
  "slate_type": "historical_validation_slate",
  "warnings": %s,
  "generated_output_paths": []
}
""".strip()
        % (run_date, run_date, generated_at, str(warnings).replace("'", '"')),
        encoding="utf-8",
    )
    (run_dir / "run_summary.md").write_text(
        "# Run Summary\n\nData Support / Risk Context only.\n\nNo betting recommendation.",
        encoding="utf-8",
    )
    (run_dir / "club_slate_projections.csv").write_text(
        "home_team,away_team,projection_profile,confidence_label\nRed FC,Blue FC,score_projection,Medium\n",
        encoding="utf-8",
    )


def test_pytest_markers_registered_and_slow_suites_marked():
    config = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "quick:" in config
    assert "slow:" in config
    assert "integration:" in config
    assert "real_data_optional:" in config
    assert "pytest.mark.slow" in (ROOT / "tests" / "test_phase18_viewer.py").read_text(encoding="utf-8")
    assert "pytest.mark.integration" in (ROOT / "tests" / "test_phase17_currentness_performance.py").read_text(encoding="utf-8")


def test_quick_test_command_can_run_subset(tmp_path):
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n    quick: quick tests\n    slow: slow tests\n",
        encoding="utf-8",
    )
    sample = tmp_path / "test_marker_sample.py"
    sample.write_text(
        """
import pytest

@pytest.mark.quick
def test_fast():
    assert True

@pytest.mark.slow
def test_slow():
    assert True
""".strip(),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(sample), "-m", "quick", "-q"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "1 passed" in result.stdout


def test_run_today_cli_wrapper_uses_operational_defaults(monkeypatch, capsys):
    captured = {}

    def fake_run_daily_pipeline(**kwargs):
        captured.update(kwargs)
        return {
            "status": "success",
            "run_dir": Path("outputs/runs/2026-05-25"),
            "manifest_path": Path("outputs/runs/2026-05-25/run_manifest.json"),
            "summary_path": Path("outputs/runs/2026-05-25/run_summary.md"),
            "warnings": [],
            "viewer": {"viewer_output_path": "outputs/viewer/index.html", "safety_scan_status": "pass"},
        }

    monkeypatch.setattr(cli, "run_daily_pipeline", fake_run_daily_pipeline)
    cli.main(["run-today", "--as-of-date", "2026-05-25", "--skip-download", "--max-matches", "5"])
    out = capsys.readouterr().out
    assert captured["as_of_date"] == "2026-05-25"
    assert captured["currentness_policy"] == "warn"
    assert captured["reuse_processed_if_fresh"] is True
    assert captured["build_viewer"] is True
    assert captured["skip_profile_comparison"] is True
    assert captured["max_matches"] == 5
    assert "Viewer: outputs/viewer/index.html" in out


def test_workflow_scripts_exist():
    for script in [
        "scripts/test_quick.ps1",
        "scripts/test_full.ps1",
        "scripts/run_today.ps1",
        "scripts/build_viewer.ps1",
        "scripts/open_viewer.ps1",
    ]:
        assert (ROOT / script).exists()


def test_viewer_polish_latest_first_and_wording(tmp_path):
    runs = tmp_path / "runs"
    _minimal_run(runs / "2026-05-24", "2026-05-24", "2026-06-24T10:00:00+00:00")
    _minimal_run(runs / "2026-05-25", "2026-05-25", "2026-06-24T11:00:00+00:00", ["Completed-season note."])
    result = build_static_viewer(runs, tmp_path / "viewer")
    index = Path(result["viewer_output_path"]).read_text(encoding="utf-8")
    detail = (tmp_path / "viewer" / "runs" / "2026-05-25.html").read_text(encoding="utf-8")
    assert index.index("2026-05-25") < index.index("2026-05-24")
    assert "Latest Run" in index
    assert "Data Support / Risk Context" in index
    assert "season_completed" in index
    assert "Warnings" in detail
    assert "club_slate_projections.csv" in detail


def test_health_check_includes_workflow_checks():
    result = run_operational_health_check()
    names = {check["name"] for check in result["checks"]}
    assert "script_scripts/test_quick.ps1" in names
    assert "script_scripts/run_today.ps1" in names
    assert "doc_docs/V1_WORKFLOW.md" in names
    assert "doc_docs/TESTING_STRATEGY.md" in names
    assert any("run-today" in check["message"] for check in result["checks"])


def test_generated_output_folders_remain_ignored():
    for path in [
        "outputs/runs/example/run_manifest.json",
        "outputs/run_logs/example.csv",
        "outputs/viewer/index.html",
        "outputs/reports/example.md",
        "outputs/projections/example.csv",
        "data/processed/example.csv",
        "data/raw/football-data/E0_2526.csv",
        "data/raw/statsbomb-open-data/example.json",
    ]:
        result = subprocess.run(["git", "check-ignore", path], cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, path


def test_guardrail_wording_and_proxy_defaults():
    report_source = (ROOT / "src" / "reports" / "slate_report.py").read_text(encoding="utf-8")
    viewer_source = (ROOT / "src" / "viewer" / "static_viewer.py").read_text(encoding="utf-8")
    assert "Data Support / Risk Context" in report_source
    assert "Data Support / Risk Context" in viewer_source
    assert "best bet" not in (report_source + viewer_source).lower()
    assert "betting pick" not in (report_source + viewer_source).lower()
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
