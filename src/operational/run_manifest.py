from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _git_value(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    return value or None


def build_run_manifest(
    run_id: str,
    run_date: str,
    input_files: list[str],
    leagues: list[str],
    season_code: str,
    downloaded_files_status: list[dict[str, Any]],
    normalized_row_counts: dict[str, Any],
    slate_type: str,
    profiles_run: list[str],
    defaults_used: dict[str, Any],
    guardrails_active: dict[str, Any],
    warnings: list[str],
    generated_output_paths: list[str],
    status: str = "success",
    currentness_status: str | None = None,
    season_sanity_status: str | None = None,
    error_message: str = "",
    timing: dict[str, Any] | None = None,
    processed_freshness: dict[str, Any] | None = None,
    viewer_output_path: str = "",
    processed_reuse_status: str = "unknown",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "run_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "currentness_status": currentness_status,
        "season_sanity_status": season_sanity_status,
        "error_message": error_message,
        "timing": timing or {},
        "processed_freshness": processed_freshness or {},
        "viewer_output_path": viewer_output_path,
        "processed_reuse_status": processed_reuse_status,
        "git_branch": _git_value(["branch", "--show-current"]),
        "git_commit": _git_value(["rev-parse", "--short", "HEAD"]),
        "input_files_used": input_files,
        "leagues": leagues,
        "season_code": season_code,
        "downloaded_files_status": downloaded_files_status,
        "normalized_row_counts": normalized_row_counts,
        "slate_type": slate_type,
        "profiles_run": profiles_run,
        "defaults_used": defaults_used,
        "guardrails_active": guardrails_active,
        "warnings": warnings,
        "generated_output_paths": generated_output_paths,
    }


def write_run_manifest(manifest: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return path
