from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import src.cli as cli
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.operational.v1_validation import audit_generated_output_ignores, scan_guardrail_language, validate_v1
from src.version import __version__


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.quick


def test_version_marker_exists():
    assert __version__ == "0.1.0-free-v1"
    assert (ROOT / "src" / "version.py").exists()


def test_v1_release_docs_exist():
    for path in [
        "docs/V1_RELEASE_NOTES.md",
        "docs/V1_LIMITATIONS.md",
        "docs/V1_RUN_CHECKLIST.md",
    ]:
        assert (ROOT / path).exists()


def test_readme_contains_v1_quick_start_commands():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for text in [
        "0.1.0-free-v1",
        ".\\scripts\\run_today.ps1",
        "run-today",
        "--skip-download",
        "include-international",
        "validate-v1",
        "outputs/viewer/index.html",
    ]:
        assert text in readme


def test_validate_v1_command_works():
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "validate-v1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "v1_status: pass" in result.stdout


def test_v1_validation_passes_on_local_repo_state():
    result = validate_v1()
    assert result["v1_status"] == "pass"
    assert any(check["name"] == "version" and check["status"] == "pass" for check in result["checks"])


def test_guardrail_scan_allows_disclaimers_and_flags_action_language(tmp_path):
    ok = tmp_path / "ok.md"
    bad = tmp_path / "bad.md"
    ok.write_text("No betting recommendation. This is not betting advice.", encoding="utf-8")
    bad.write_text("Bet this. This is a lock.", encoding="utf-8")
    assert scan_guardrail_language([str(ok)])["guardrail_scan_status"] == "pass"
    result = scan_guardrail_language([str(bad)])
    assert result["guardrail_scan_status"] == "warning"
    assert result["warnings"]


def test_generated_file_tracking_audit_checks_ignored_folders():
    result = audit_generated_output_ignores()
    assert result["audit_status"] == "pass"
    checked = {check["name"] for check in result["checks"]}
    assert "ignored:outputs/runs/example/run_manifest.json" in checked
    assert "ignored:outputs/viewer/index.html" in checked
    assert "ignored:data/processed/example.csv" in checked


def test_release_commands_and_scripts_still_exist():
    parser = cli.build_parser()
    commands = parser._subparsers._group_actions[0].choices
    for command in ["run-today", "build-report-viewer", "open-report-viewer", "validate-v1"]:
        assert command in commands
    for script in [
        "scripts/test_quick.ps1",
        "scripts/test_full.ps1",
        "scripts/run_today.ps1",
        "scripts/build_viewer.ps1",
        "scripts/open_viewer.ps1",
        "scripts/validate_v1.ps1",
    ]:
        assert (ROOT / script).exists()


def test_proxy_adjustments_remain_disabled_by_default():
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
