from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.viewer.html_formatting import csv_to_html_table, escape_html, markdown_to_html, unordered_list
from src.viewer.run_index import build_run_index


PROHIBITED_TERMS = ("bet", "take", "play", "lock", "pick", "wager")
DISCLAIMER_PATTERNS = (
    "no betting",
    "not a betting",
    "not betting",
    "betting recommendation",
    "betting recommendations",
    "no wagering",
    "not a wagering",
    "not wagering",
    "guardrail",
)


CSS = """
:root { color-scheme: light; font-family: Arial, Helvetica, sans-serif; }
body { margin: 0; background: #f7f7f4; color: #202124; }
header { background: #12343b; color: white; padding: 24px 32px; }
main { max-width: 1180px; margin: 0 auto; padding: 24px 20px 48px; }
h1, h2, h3 { letter-spacing: 0; }
a { color: #0b5d7a; }
.notice { background: #fff; border: 1px solid #d8d8d0; border-left: 4px solid #2f7d57; padding: 12px 14px; margin: 16px 0; }
.warning { border-left-color: #b66a00; }
.status-pill { display: inline-block; padding: 3px 8px; border-radius: 999px; background: #e8f1ec; font-size: 12px; font-weight: 700; }
.status-warn { background: #fff1d7; }
.status-fail { background: #f8d7da; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.metric { background: #fff; border: 1px solid #d8d8d0; padding: 12px; border-radius: 6px; }
.metric span { display: block; color: #5f6368; font-size: 12px; margin-bottom: 4px; }
.table-wrap { overflow-x: auto; background: #fff; border: 1px solid #d8d8d0; border-radius: 6px; margin: 12px 0 24px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { padding: 8px 10px; border-bottom: 1px solid #e6e6df; text-align: left; vertical-align: top; }
th { background: #ecece4; font-weight: 700; }
tr.latest td { background: #f0f7f2; }
.muted { color: #6f7377; }
.report { background: #fff; border: 1px solid #d8d8d0; border-radius: 6px; padding: 16px; margin-bottom: 20px; }
pre { overflow-x: auto; background: #202124; color: #f7f7f4; padding: 12px; border-radius: 6px; }
"""


def _status_class(status: object) -> str:
    text = str(status or "").lower()
    if text.startswith("failed") or "unsafe" in text:
        return "status-pill status-fail"
    if "warning" in text or "stale" in text or "probably" in text:
        return "status-pill status-warn"
    return "status-pill"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def scan_report_safety(paths: list[Path]) -> dict[str, Any]:
    warnings: list[str] = []
    for path in paths:
        text = _read_text(path)
        for number, line in enumerate(text.splitlines(), start=1):
            lower = line.lower()
            if any(pattern in lower for pattern in DISCLAIMER_PATTERNS):
                continue
            for term in PROHIBITED_TERMS:
                if re.search(rf"\b{re.escape(term)}\b", lower):
                    warnings.append(f"{path.name}:{number} contains action term '{term}'")
                    break
    return {
        "safety_scan_status": "warning" if warnings else "pass",
        "safety_warnings": warnings,
    }


def _run_detail_page(entry: dict[str, Any], output_dir: Path) -> tuple[str, dict[str, Any]]:
    run_dir = Path(entry["run_dir"])
    run_id = str(entry.get("run_id") or entry.get("run_date"))
    detail_path = output_dir / "runs" / f"{run_id}.html"
    detail_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_paths = [
        path for path in [
            run_dir / "run_summary.md",
            run_dir / "club_slate_report.md",
            run_dir / "international_slate_report.md",
            run_dir / "projection_profile_comparison.md",
        ] if path.exists()
    ]
    safety = scan_report_safety(markdown_paths)
    sections = [
        "<!doctype html><html><head><meta charset=\"utf-8\">",
        f"<title>Run {escape_html(run_id)}</title>",
        f"<style>{CSS}</style></head><body>",
        f"<header><h1>Run {escape_html(run_id)}</h1><p>Run date {escape_html(entry.get('run_date'))} | Generated {escape_html(entry.get('generated_at'))}</p></header><main>",
        "<div class=\"notice\"><strong>Guardrail:</strong> This viewer reads generated outputs only. It does not recompute projections, create betting recommendations, or claim proxy metrics are true event/tracking style.</div>",
        "<div class=\"notice\"><strong>Interpretation:</strong> probability and support fields are Data Support / Risk Context, not certainty and not a recommendation.</div>",
        "<section class=\"grid\">",
        f"<div class=\"metric\"><span>Status</span><span class=\"{_status_class(entry.get('status'))}\">{escape_html(entry.get('status'))}</span></div>",
        f"<div class=\"metric\"><span>Currentness</span><span class=\"{_status_class(entry.get('currentness_status'))}\">{escape_html(entry.get('currentness_status'))}</span></div>",
        f"<div class=\"metric\"><span>Season sanity</span><span class=\"{_status_class(entry.get('season_sanity_status'))}\">{escape_html(entry.get('season_sanity_status'))}</span></div>",
        f"<div class=\"metric\"><span>Rows</span>{escape_html(entry.get('row_count'))}</div>",
        f"<div class=\"metric\"><span>Warnings</span>{escape_html(entry.get('warnings_count'))}</div>",
        f"<div class=\"metric\"><span>Slate type</span>{escape_html(entry.get('slate_type'))}</div>",
        "</section>",
        "<h2>Run Output Paths</h2>",
        unordered_list(entry.get("output_files_present") or []),
        "<h2>Warnings</h2>",
        unordered_list(entry.get("warnings") or []),
        "<h2>Safety Scan</h2>",
        f"<p>Status: <strong>{escape_html(safety['safety_scan_status'])}</strong></p>",
        unordered_list(safety["safety_warnings"]),
    ]
    for title, filename in [
        ("Club Slate", "club_slate_projections.csv"),
        ("International Slate", "international_slate_projections.csv"),
        ("Profile Comparison", "projection_profile_comparison.csv"),
    ]:
        path = run_dir / filename
        if path.exists():
            sections.append(f"<h2>{escape_html(title)}</h2>")
            sections.append(csv_to_html_table(path))
    for path in markdown_paths:
        sections.append(f"<section class=\"report\"><h2>{escape_html(path.name)}</h2>")
        sections.append(markdown_to_html(_read_text(path)))
        sections.append("</section>")
    sections.extend(["</main></body></html>"])
    detail_path.write_text("\n".join(sections), encoding="utf-8")
    return str(detail_path), safety


def _index_table(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "<p class=\"muted\">No runs found.</p>"
    latest_run_id = entries[0].get("run_id")
    rows = ["<div class=\"table-wrap\"><table><thead><tr>"]
    for header in ["date", "status", "currentness", "season", "rows", "warnings", "slate_type", "detail"]:
        rows.append(f"<th>{escape_html(header)}</th>")
    rows.append("</tr></thead><tbody>")
    for entry in entries:
        run_id = str(entry.get("run_id") or entry.get("run_date"))
        cls = " class=\"latest\"" if run_id == latest_run_id else ""
        rows.append(f"<tr{cls}>")
        rows.append(f"<td>{escape_html(entry.get('run_date'))}</td>")
        rows.append(f"<td><span class=\"{_status_class(entry.get('status'))}\">{escape_html(entry.get('status'))}</span></td>")
        rows.append(f"<td><span class=\"{_status_class(entry.get('currentness_status'))}\">{escape_html(entry.get('currentness_status'))}</span></td>")
        rows.append(f"<td>{escape_html(entry.get('season_sanity_status'))}</td>")
        rows.append(f"<td>{escape_html(entry.get('row_count'))}</td>")
        rows.append(f"<td>{escape_html(entry.get('warnings_count'))}</td>")
        rows.append(f"<td>{escape_html(entry.get('slate_type'))}</td>")
        rows.append(f"<td><a href=\"runs/{escape_html(run_id)}.html\">Open</a></td>")
        rows.append("</tr>")
    rows.append("</tbody></table></div>")
    return "\n".join(rows)


def _latest_summary(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return ""
    latest = entries[0]
    return "\n".join([
        "<section class=\"notice\">",
        "<h2>Latest Run</h2>",
        f"<p><strong>{escape_html(latest.get('run_date'))}</strong> | "
        f"<span class=\"{_status_class(latest.get('status'))}\">{escape_html(latest.get('status'))}</span> | "
        f"Currentness: <span class=\"{_status_class(latest.get('currentness_status'))}\">{escape_html(latest.get('currentness_status'))}</span> | "
        f"Warnings: {escape_html(latest.get('warnings_count'))}</p>",
        f"<p class=\"muted\">Generated at {escape_html(latest.get('generated_at'))}. Row count: {escape_html(latest.get('row_count'))}. Slate type: {escape_html(latest.get('slate_type'))}.</p>",
        "</section>",
    ])


def build_static_viewer(runs_root: str | Path = "outputs/runs", output_dir: str | Path = "outputs/viewer") -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    entries = build_run_index(runs_root)
    detail_pages: list[str] = []
    safety_warnings: list[str] = []
    for entry in entries:
        page, safety = _run_detail_page(entry, output)
        detail_pages.append(page)
        safety_warnings.extend(safety["safety_warnings"])
    status = "warning" if safety_warnings else "pass"
    index_path = output / "index.html"
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = "\n".join([
        "<!doctype html><html><head><meta charset=\"utf-8\">",
        "<title>Soccer Style Engine Report Viewer</title>",
        f"<style>{CSS}</style></head><body>",
        "<header><h1>Soccer Style Engine Report Viewer</h1><p>Local static view of generated run outputs.</p></header><main>",
        f"<p class=\"muted\">Generated at {escape_html(generated_at)}</p>",
        "<div class=\"notice\"><strong>Source of truth:</strong> this viewer reads files under the run output folder. It does not recompute projections or modify model logic.</div>",
        "<div class=\"notice\"><strong>Guardrails:</strong> no betting recommendations, no paid data dependencies, no dashboard/event visuals, and free proxy metrics are not true event/tracking style.</div>",
        "<div class=\"notice\"><strong>Data Support / Risk Context:</strong> displayed support labels are context for review, not certainty and not recommendations.</div>",
        _latest_summary(entries),
        "<h2>Runs</h2>",
        _index_table(entries),
        "<h2>Safety Scan</h2>",
        f"<p>Status: <strong>{escape_html(status)}</strong></p>",
        unordered_list(safety_warnings),
        "</main></body></html>",
    ])
    index_path.write_text(html, encoding="utf-8")
    return {
        "viewer_output_path": str(index_path),
        "runs_included": len(entries),
        "run_pages": detail_pages,
        "safety_scan_status": status,
        "safety_warnings": safety_warnings,
    }
