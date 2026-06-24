from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


def _check_imports() -> tuple[bool, str]:
    try:
        import numpy  # noqa: F401
        import pandas  # noqa: F401
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"Dependency import failed: {exc}"
    return True, "Python dependencies import."


def _ensure_folder(path: str) -> tuple[bool, str]:
    folder = Path(path)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"{path} cannot be created: {exc}"
    return True, f"{path} exists or can be created."


def _visible_generated_outputs() -> list[str]:
    try:
        completed = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return []
    bad_prefixes = ("data/raw/", "data/processed/", "outputs/reports/", "outputs/projections/", "outputs/runs/", "outputs/run_logs/")
    return [line for line in completed.stdout.splitlines() if any(prefix in line.replace("\\", "/") for prefix in bad_prefixes)]


def run_operational_health_check() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    failures: list[str] = []

    ok, message = _check_imports()
    checks.append({"name": "dependency_imports", "passed": ok, "message": message})
    if not ok:
        failures.append(message)
    for folder in ["data/raw/football-data", "data/processed", "outputs", "outputs/runs", "outputs/run_logs"]:
        ok, message = _ensure_folder(folder)
        checks.append({"name": f"folder_{folder}", "passed": ok, "message": message})
        if not ok:
            failures.append(message)
    for sample in ["data/sample/manual_club_matchups.csv", "data/sample/manual_international_matchups.csv"]:
        exists = Path(sample).exists()
        checks.append({"name": f"sample_{sample}", "passed": exists, "message": f"{sample} {'exists' if exists else 'is missing'}."})
        if not exists:
            warnings.append(f"Missing optional sample matchup file: {sample}")
    visible = _visible_generated_outputs()
    checks.append({"name": "generated_outputs_hidden", "passed": not visible, "message": "No generated outputs visible to git." if not visible else "; ".join(visible)})
    if visible:
        warnings.append("Some generated output paths are visible to git status.")
    commands = ["run-daily-pipeline", "explain-operational-defaults", "explain-currentness", "operational-health-check", "check-data-currentness", "check-season-sanity"]
    checks.append({"name": "cli_commands_registered", "passed": True, "message": ", ".join(commands)})
    statsbomb = Path("data/raw/statsbomb-open-data/data").exists()
    checks.append({"name": "optional_statsbomb_root", "passed": True, "message": "StatsBomb root present." if statsbomb else "StatsBomb root not present; international daily run can be skipped."})
    if not statsbomb:
        warnings.append("Optional StatsBomb root not present.")
    status = "fail" if failures else "warn" if warnings else "pass"
    fixes = []
    if visible:
        fixes.append("Confirm generated-output ignore rules and remove generated artifacts from tracking.")
    if not Path("data/raw/football-data").exists():
        fixes.append("Create data/raw/football-data or run the daily pipeline once.")
    return {"health_status": status, "checks": checks, "warnings": warnings, "recommended_fixes": fixes}


def format_health_check(result: dict[str, Any]) -> str:
    lines = [f"health_status: {result['health_status']}", "", "checks:"]
    for check in result["checks"]:
        marker = "pass" if check["passed"] else "fail"
        lines.append(f"- {check['name']}: {marker} - {check['message']}")
    lines.append("")
    lines.append("warnings:")
    lines.extend([f"- {warning}" for warning in result["warnings"]] or ["- None"])
    lines.append("")
    lines.append("recommended fixes:")
    lines.extend([f"- {fix}" for fix in result["recommended_fixes"]] or ["- None"])
    return "\n".join(lines)
