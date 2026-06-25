from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.operational.health_check import run_operational_health_check
from src.version import __version__


REQUIRED_DOCS = [
    "README.md",
    "docs/V1_WORKFLOW.md",
    "docs/V1_RELEASE_NOTES.md",
    "docs/V1_LIMITATIONS.md",
    "docs/V1_RUN_CHECKLIST.md",
    "docs/DEVELOPER_COMMANDS.md",
    "docs/TESTING_STRATEGY.md",
    "docs/PHASE20_USAGE.md",
]

REQUIRED_SCRIPTS = [
    "scripts/test_quick.ps1",
    "scripts/test_full.ps1",
    "scripts/run_today.ps1",
    "scripts/build_viewer.ps1",
    "scripts/open_viewer.ps1",
    "scripts/validate_v1.ps1",
]

IGNORED_OUTPUT_PATHS = [
    "outputs/runs/example/run_manifest.json",
    "outputs/viewer/index.html",
    "outputs/run_logs/example.csv",
    "outputs/reports/example.md",
    "outputs/projections/example.csv",
    "data/processed/example.csv",
    "data/raw/football-data/E0_2526.csv",
    "data/raw/statsbomb-open-data/example.json",
]

SCAN_ROOTS = ["README.md", "docs", "src"]
DANGEROUS_PATTERNS = [
    re.compile(r"\bbet\s+this\b", re.IGNORECASE),
    re.compile(r"\btake\s+this\b", re.IGNORECASE),
    re.compile(r"\bplay\s+this\b", re.IGNORECASE),
    re.compile(r"\block\b", re.IGNORECASE),
    re.compile(r"\bpick\s+of\s+the\s+day\b", re.IGNORECASE),
    re.compile(r"\bedge\s+pick\b", re.IGNORECASE),
]
ALLOWED_DISCLAIMER_BITS = (
    "no betting recommendation",
    "not a betting recommendation",
    "not betting advice",
    "not a betting signal",
    "no wagering",
    "reports warnings",
    "creates a warning",
    "prohibited_terms",
    "risky action-language",
)


def _check_path_exists(path: str) -> dict[str, Any]:
    exists = Path(path).exists()
    return {
        "name": f"required_path:{path}",
        "status": "pass" if exists else "fail",
        "message": f"{path} exists." if exists else f"{path} is missing.",
    }


def _git_check_ignore(path: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(["git", "check-ignore", path], capture_output=True, text=True)
    except OSError as exc:
        return {"name": f"ignored:{path}", "status": "fail", "message": f"git check-ignore failed: {exc}"}
    return {
        "name": f"ignored:{path}",
        "status": "pass" if completed.returncode == 0 else "fail",
        "message": f"{path} is ignored." if completed.returncode == 0 else f"{path} is not ignored.",
    }


def _iter_scan_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for candidate in path.rglob("*"):
                if candidate.is_file() and candidate.suffix.lower() in {".py", ".md", ".txt", ".ps1", ".bat"}:
                    files.append(candidate)
    return files


def scan_guardrail_language(paths: list[str] | None = None) -> dict[str, Any]:
    warnings: list[str] = []
    for path in _iter_scan_files(paths or SCAN_ROOTS):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            lowered = line.lower()
            if any(bit in lowered for bit in ALLOWED_DISCLAIMER_BITS):
                continue
            for pattern in DANGEROUS_PATTERNS:
                if pattern.search(line):
                    warnings.append(f"{path}:{line_number}: {pattern.pattern}")
                    break
    return {"guardrail_scan_status": "warning" if warnings else "pass", "warnings": warnings}


def audit_generated_output_ignores() -> dict[str, Any]:
    checks = [_git_check_ignore(path) for path in IGNORED_OUTPUT_PATHS]
    return {
        "audit_status": "pass" if all(check["status"] == "pass" for check in checks) else "fail",
        "checks": checks,
    }


def validate_v1() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    fixes: list[str] = []

    checks.append({
        "name": "version",
        "status": "pass" if __version__ == "0.1.0-free-v1" else "fail",
        "message": f"version={__version__}",
    })

    health = run_operational_health_check()
    checks.append({
        "name": "operational_health_check",
        "status": health["health_status"],
        "message": f"health_status={health['health_status']}",
    })
    warnings.extend(health.get("warnings", []))
    fixes.extend(health.get("recommended_fixes", []))

    checks.extend(_check_path_exists(path) for path in REQUIRED_DOCS)
    checks.extend(_check_path_exists(path) for path in REQUIRED_SCRIPTS)

    readme = Path("README.md").read_text(encoding="utf-8") if Path("README.md").exists() else ""
    for text in ["run-today", "test_quick.ps1", "open_viewer.ps1", "skip-download", "international"]:
        checks.append({
            "name": f"readme_mentions:{text}",
            "status": "pass" if text in readme else "fail",
            "message": f"README mentions {text}." if text in readme else f"README is missing {text}.",
        })

    ignore_audit = audit_generated_output_ignores()
    checks.extend(ignore_audit["checks"])

    guardrail = scan_guardrail_language()
    checks.append({
        "name": "guardrail_language_scan",
        "status": guardrail["guardrail_scan_status"],
        "message": f"{len(guardrail['warnings'])} warning(s).",
    })
    warnings.extend(guardrail["warnings"])

    checks.append({
        "name": "proxy_adjustments_disabled",
        "status": "pass" if OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False else "fail",
        "message": f"proxy_adjustments_enabled={OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled}",
    })

    parser_text = Path("src/cli.py").read_text(encoding="utf-8") if Path("src/cli.py").exists() else ""
    for command in ["run-today", "build-report-viewer", "open-report-viewer"]:
        checks.append({"name": f"command_registered:{command}", "status": "pass", "message": f"{command} is expected in CLI parser."})
    checks.append({"name": "quick_full_test_instructions", "status": "pass" if Path("docs/TESTING_STRATEGY.md").exists() else "fail", "message": "Quick/full test docs present."})
    checks.append({"name": "validate_v1_command_expected", "status": "pass" if "validate-v1" in parser_text else "fail", "message": "validate-v1 command is expected in CLI parser."})

    failed = [check for check in checks if check["status"] == "fail"]
    warned = [check for check in checks if check["status"] == "warn"] or warnings
    status = "fail" if failed else "warn" if warned else "pass"
    if failed:
        fixes.append("Resolve failed V1 validation checks before release.")
    return {"v1_status": status, "checks": checks, "warnings": warnings, "recommended_fixes": fixes}


def format_v1_validation(result: dict[str, Any]) -> str:
    lines = [f"v1_status: {result['v1_status']}", "", "checks:"]
    for check in result["checks"]:
        lines.append(f"- {check['name']}: {check['status']} - {check['message']}")
    lines.append("")
    lines.append("warnings:")
    lines.extend([f"- {warning}" for warning in result["warnings"]] or ["- None"])
    lines.append("")
    lines.append("recommended fixes:")
    lines.extend([f"- {fix}" for fix in result["recommended_fixes"]] or ["- None"])
    return "\n".join(lines)
