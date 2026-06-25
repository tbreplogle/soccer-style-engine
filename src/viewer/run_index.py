from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RUN_OUTPUT_NAMES = (
    "run_manifest.json",
    "run_summary.md",
    "club_slate_projections.csv",
    "international_slate_projections.csv",
    "projection_profile_comparison.csv",
    "club_slate_report.md",
    "international_slate_report.md",
    "projection_profile_comparison.md",
    "leakage_audit_summary.md",
)

CHECKPOINT_OUTPUT_NAMES = (
    "projection_checkpoint_manifest.json",
    "projection_checkpoint_summary.md",
    "projection_checkpoint_rows.csv",
    "projection_checkpoint_flags.csv",
    "poisson/poisson_summary.md",
    "poisson/poisson_match_summary.csv",
    "poisson/poisson_correct_score_matrix.csv",
)


def _empty_entry(run_dir: Path, error: str = "") -> dict[str, Any]:
    present = sorted(path.name for path in run_dir.iterdir()) if run_dir.exists() and run_dir.is_dir() else []
    return {
        "entry_type": "daily_run",
        "run_date": run_dir.name,
        "run_id": run_dir.name,
        "generated_at": "",
        "status": "missing_manifest" if error != "empty_run_folder" else "empty_run_folder",
        "currentness_status": "unknown",
        "season_sanity_status": "unknown",
        "leagues": [],
        "row_count": 0,
        "slate_type": "unknown",
        "warnings_count": 0,
        "warnings": [],
        "output_files_present": present,
        "manifest_path": "",
        "summary_path": str(run_dir / "run_summary.md") if (run_dir / "run_summary.md").exists() else "",
        "run_dir": str(run_dir),
        "error": error,
    }


def _manifest_entry(run_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry = _empty_entry(run_dir, "malformed_manifest")
        entry["status"] = "malformed_manifest"
        entry["manifest_path"] = str(manifest_path)
        entry["error"] = str(exc)
        return entry

    row_counts = manifest.get("normalized_row_counts") or {}
    warnings = manifest.get("warnings") or []
    summary_path = run_dir / "run_summary.md"
    present = [name for name in RUN_OUTPUT_NAMES if (run_dir / name).exists()]
    return {
        "entry_type": "daily_run",
        "run_date": str(manifest.get("run_date") or run_dir.name),
        "run_id": str(manifest.get("run_id") or run_dir.name),
        "generated_at": str(manifest.get("generated_at") or ""),
        "status": str(manifest.get("status") or "unknown"),
        "currentness_status": str(manifest.get("currentness_status") or "unknown"),
        "season_sanity_status": str(manifest.get("season_sanity_status") or "unknown"),
        "leagues": list(manifest.get("leagues") or []),
        "row_count": int(row_counts.get("total_rows") or 0),
        "slate_type": str(manifest.get("slate_type") or "unknown"),
        "warnings_count": len(warnings),
        "warnings": warnings,
        "output_files_present": present,
        "manifest_path": str(manifest_path),
        "summary_path": str(summary_path) if summary_path.exists() else "",
        "run_dir": str(run_dir),
        "error": str(manifest.get("error_message") or ""),
    }


def _checkpoint_entry(checkpoint_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry = _empty_entry(checkpoint_dir, "malformed_checkpoint_manifest")
        entry["entry_type"] = "projection_checkpoint"
        entry["status"] = "malformed_checkpoint_manifest"
        entry["manifest_path"] = str(manifest_path)
        entry["error"] = str(exc)
        return entry

    present = [name for name in CHECKPOINT_OUTPUT_NAMES if (checkpoint_dir / name).exists()]
    warnings_count = int(manifest.get("warning_count") or 0)
    return {
        "entry_type": "projection_checkpoint",
        "run_date": str(manifest.get("run_date") or checkpoint_dir.name),
        "run_id": str(manifest.get("run_id") or f"projection_checkpoint_{checkpoint_dir.name}"),
        "generated_at": str(manifest.get("generated_at") or ""),
        "status": str(manifest.get("status") or "unknown"),
        "currentness_status": "projection_checkpoint",
        "season_sanity_status": "not_applicable",
        "leagues": [],
        "row_count": int(manifest.get("rows_reviewed") or 0),
        "slate_type": "projection_checkpoint",
        "warnings_count": warnings_count,
        "warnings": [f"{warnings_count} projection checkpoint warning flags"] if warnings_count else [],
        "output_files_present": present,
        "manifest_path": str(manifest_path),
        "summary_path": str(checkpoint_dir / "projection_checkpoint_summary.md") if (checkpoint_dir / "projection_checkpoint_summary.md").exists() else "",
        "run_dir": str(checkpoint_dir),
        "error": "",
        "source_projection_file": str(manifest.get("source_projection_file") or ""),
    }


def _iter_run_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for run_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda p: p.name, reverse=True):
        if not any(run_dir.iterdir()):
            entries.append(_empty_entry(run_dir, "empty_run_folder"))
            continue
        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.exists():
            entries.append(_empty_entry(run_dir, "missing_manifest"))
            continue
        entries.append(_manifest_entry(run_dir, manifest_path))
    return entries


def _iter_checkpoint_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not root.exists() or not root.is_dir():
        return entries
    for checkpoint_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda p: p.name, reverse=True):
        manifest_path = checkpoint_dir / "projection_checkpoint_manifest.json"
        if manifest_path.exists():
            entries.append(_checkpoint_entry(checkpoint_dir, manifest_path))
    return entries


def build_run_index(runs_root: str | Path = "outputs/runs") -> list[dict[str, Any]]:
    root = Path(runs_root)
    if not root.exists() or not root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    run_roots = [root]
    if (root / "runs").exists() and root.name != "runs":
        run_roots = [root / "runs"]
    elif (root / "projection_checkpoints").exists() and root.name != "runs":
        run_roots = []
    for run_root in run_roots:
        if run_root.exists() and run_root.is_dir():
            entries.extend(_iter_run_entries(run_root))

    checkpoint_root = root if root.name == "projection_checkpoints" else root / "projection_checkpoints"
    entries.extend(_iter_checkpoint_entries(checkpoint_root))
    return sorted(entries, key=lambda item: (item.get("run_date", ""), item.get("generated_at", "")), reverse=True)


def format_run_index_table(entries: list[dict[str, Any]]) -> str:
    headers = ["date", "type", "status", "currentness", "rows", "warnings", "slate_type"]
    rows = [
        [
            item.get("run_date", ""),
            item.get("entry_type", "daily_run"),
            item.get("status", ""),
            item.get("currentness_status", ""),
            str(item.get("row_count", 0)),
            str(item.get("warnings_count", 0)),
            item.get("slate_type", ""),
        ]
        for item in entries
    ]
    if not rows:
        return "No runs found."
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, widths))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend("  ".join(value.ljust(width) for value, width in zip(row, widths)) for row in rows)
    return "\n".join(lines)
