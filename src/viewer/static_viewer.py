from __future__ import annotations

import csv
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
.match-card { background: #fff; border: 1px solid #d8d8d0; border-radius: 8px; padding: 16px; margin: 18px 0; }
.card-title { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; align-items: baseline; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.badge { display: inline-block; padding: 3px 8px; border-radius: 999px; background: #ecece4; font-size: 12px; font-weight: 700; }
.badge-warn { background: #fff1d7; }
.prob-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin: 12px 0; }
.prob-tile { border: 1px solid #e0e0d8; background: #fbfbf7; padding: 10px; border-radius: 6px; }
.prob-tile span { display: block; color: #5f6368; font-size: 12px; }
.prob-tile strong { font-size: 18px; }
.board-link { font-weight: 700; }
.score-grid table { table-layout: fixed; }
.score-grid td { text-align: center; font-size: 12px; }
.score-grid small { display: block; color: #6f7377; margin-top: 2px; }
.highlight-row td { background: #fff8e6; }
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


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(value: object) -> str:
    return f"{_float(value) * 100:.1f}%"


def _odds(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    return text if text.startswith(("+", "-")) else f"+{text}"


def _match_key(row: dict[str, str]) -> tuple[str, str]:
    return str(row.get("home_team", "")), str(row.get("away_team", ""))


def _artifact_links(run_date: str) -> str:
    names = [
        ("Checkpoint summary", f"../../../projection_checkpoints/{run_date}/projection_checkpoint_summary.md"),
        ("Checkpoint manifest", f"../../../projection_checkpoints/{run_date}/projection_checkpoint_manifest.json"),
        ("Poisson summary", f"../../../projection_checkpoints/{run_date}/poisson/poisson_summary.md"),
        ("Match summary CSV", f"../../../projection_checkpoints/{run_date}/poisson/poisson_match_summary.csv"),
        ("1X2 CSV", f"../../../projection_checkpoints/{run_date}/poisson/poisson_1x2.csv"),
        ("Totals CSV", f"../../../projection_checkpoints/{run_date}/poisson/poisson_totals.csv"),
        ("BTTS CSV", f"../../../projection_checkpoints/{run_date}/poisson/poisson_btts.csv"),
        ("Clean sheets CSV", f"../../../projection_checkpoints/{run_date}/poisson/poisson_clean_sheets.csv"),
        ("Correct score matrix CSV", f"../../../projection_checkpoints/{run_date}/poisson/poisson_correct_score_matrix.csv"),
    ]
    links = [
        f"<li><a href=\"{escape_html(path)}\">{escape_html(label)}</a></li>"
        for label, path in names
    ]
    return "<ul>" + "".join(links) + "</ul>"


def _lookup_by_match(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    lookup: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        lookup.setdefault(_match_key(row), []).append(row)
    return lookup


def _single_by_match(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {(_match_key(row)): row for row in rows}


def _prob_tile(label: str, probability: object, american_odds: object) -> str:
    return (
        "<div class=\"prob-tile\">"
        f"<span>{escape_html(label)}</span>"
        f"<strong>{escape_html(_pct(probability))}</strong>"
        f"<span>Model-implied American odds {escape_html(_odds(american_odds))}</span>"
        "</div>"
    )


def _warning_items(row: dict[str, str]) -> str:
    labels = [
        ("Primary", row.get("primary_warning")),
        ("Source", row.get("source_warning")),
        ("Rating", row.get("rating_warning")),
        ("Style", row.get("style_warning")),
        ("Guardrail", row.get("guardrail_flags")),
    ]
    items = [
        f"<li><strong>{escape_html(label)}:</strong> {escape_html(value)}</li>"
        for label, value in labels
        if str(value or "").strip()
    ]
    return "<ul>" + "".join(items) + "</ul>" if items else "<p class=\"muted\">No short warning supplied.</p>"


def _totals_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p class=\"muted\">No totals rows found.</p>"
    parts = ["<div class=\"table-wrap\"><table><thead><tr><th>Line</th><th>Over</th><th>Under</th><th>Over American odds</th><th>Under American odds</th></tr></thead><tbody>"]
    for row in rows:
        cls = " class=\"highlight-row\"" if str(row.get("line")) == "2.5" else ""
        parts.append(f"<tr{cls}>")
        parts.append(f"<td>{escape_html(row.get('line'))}</td>")
        parts.append(f"<td>{escape_html(_pct(row.get('over_probability')))}</td>")
        parts.append(f"<td>{escape_html(_pct(row.get('under_probability')))}</td>")
        parts.append(f"<td>{escape_html(_odds(row.get('over_american_odds')))}</td>")
        parts.append(f"<td>{escape_html(_odds(row.get('under_american_odds')))}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "\n".join(parts)


def _top_scores_table(rows: list[dict[str, str]]) -> str:
    top = sorted(rows, key=lambda row: _float(row.get("probability")), reverse=True)[:5]
    if not top:
        return "<p class=\"muted\">No correct score rows found.</p>"
    parts = ["<div class=\"table-wrap\"><table><thead><tr><th>Score</th><th>Probability</th><th>Model-implied American odds</th></tr></thead><tbody>"]
    for row in top:
        parts.append("<tr>")
        parts.append(f"<td>{escape_html(row.get('score_label'))}</td>")
        parts.append(f"<td>{escape_html(_pct(row.get('probability')))}</td>")
        parts.append(f"<td>{escape_html(_odds(row.get('correct_score_american_odds')))}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "\n".join(parts)


def _correct_score_grid(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p class=\"muted\">No correct score grid found.</p>"
    home_goals = sorted({int(_float(row.get("home_goals"))) for row in rows})
    away_goals = sorted({int(_float(row.get("away_goals"))) for row in rows})
    lookup = {(int(_float(row.get("home_goals"))), int(_float(row.get("away_goals")))): row for row in rows}
    parts = ["<div class=\"table-wrap score-grid\"><table><thead><tr><th>Away \\ Home</th>"]
    parts.extend(f"<th>{goal}</th>" for goal in home_goals)
    parts.append("</tr></thead><tbody>")
    for away in away_goals:
        parts.append(f"<tr><th>{away}</th>")
        for home in home_goals:
            row = lookup.get((home, away), {})
            parts.append(
                "<td>"
                f"{escape_html(_pct(row.get('probability')))}"
                f"<small>{escape_html(_odds(row.get('correct_score_american_odds')))}</small>"
                "</td>"
            )
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "\n".join(parts)


def _match_card(
    row: dict[str, str],
    one_x_two: dict[str, str],
    totals: list[dict[str, str]],
    btts: dict[str, str],
    clean: dict[str, str],
    scores: list[dict[str, str]],
) -> str:
    home = row.get("home_team", "")
    away = row.get("away_team", "")
    source_tier = row.get("source_tier", "")
    style_state = "available" if str(row.get("style_inputs_available", "")).lower() == "true" else "unavailable"
    parts = [
        "<article class=\"match-card\">",
        "<div class=\"card-title\">",
        f"<h2>{escape_html(home)} vs {escape_html(away)}</h2>",
        f"<span class=\"badge\">{escape_html(source_tier or 'unknown source')}</span>",
        "</div>",
        "<div class=\"badges\">",
        f"<span class=\"badge\">Support: {escape_html(row.get('data_support_level'))}</span>",
        f"<span class=\"badge\">Confidence: {escape_html(row.get('confidence_label'))}</span>",
        f"<span class=\"badge\">Style inputs: {escape_html(style_state)}</span>",
        f"<span class=\"badge\">Rating: {escape_html(row.get('rating_status'))}</span>",
        "</div>",
        "<section class=\"grid\">",
        f"<div class=\"metric\"><span>Projected xG</span>{escape_html(home)} {escape_html(row.get('projected_home_xg'))} | {escape_html(away)} {escape_html(row.get('projected_away_xg'))}</div>",
        f"<div class=\"metric\"><span>Projected total</span>{escape_html(row.get('projected_total'))}</div>",
        f"<div class=\"metric\"><span>Most likely score</span>{escape_html(row.get('most_likely_score'))} ({escape_html(_pct(row.get('most_likely_score_probability')))}, {escape_html(_odds(row.get('most_likely_score_american_odds')))} American odds)</div>",
        "</section>",
        "<div class=\"notice warning\"><strong>Review notes</strong>",
        _warning_items(row),
        "</div>",
        "<h3>1X2 Probability Output</h3>",
        "<div class=\"prob-grid\">",
        _prob_tile(f"{home} win", one_x_two.get("home_win_probability"), one_x_two.get("home_american_odds")),
        _prob_tile("Draw", one_x_two.get("draw_probability"), one_x_two.get("draw_american_odds")),
        _prob_tile(f"{away} win", one_x_two.get("away_win_probability"), one_x_two.get("away_american_odds")),
        "</div>",
        "<h3>Totals</h3>",
        _totals_table(totals),
        "<h3>BTTS</h3>",
        "<div class=\"prob-grid\">",
        _prob_tile("BTTS yes", btts.get("yes_probability"), btts.get("btts_yes_american_odds")),
        _prob_tile("BTTS no", btts.get("no_probability"), btts.get("btts_no_american_odds")),
        "</div>",
        "<h3>Clean Sheets</h3>",
        "<div class=\"prob-grid\">",
        _prob_tile(f"{home} clean sheet", clean.get("home_clean_sheet_probability"), clean.get("home_clean_sheet_american_odds")),
        _prob_tile(f"{away} clean sheet", clean.get("away_clean_sheet_probability"), clean.get("away_clean_sheet_american_odds")),
        _prob_tile(f"{home} concedes", clean.get("home_concedes_probability"), clean.get("home_concedes_american_odds")),
        _prob_tile(f"{away} concedes", clean.get("away_concedes_probability"), clean.get("away_concedes_american_odds")),
        "</div>",
        "<h3>Top Correct Scores</h3>",
        _top_scores_table(scores),
        "<h3>Correct Score Grid</h3>",
        _correct_score_grid(scores),
        "</article>",
    ]
    return "\n".join(parts)


def _projection_checkpoint_board_page(entry: dict[str, Any], output_dir: Path) -> str | None:
    run_dir = Path(entry["run_dir"])
    run_date = str(entry.get("run_date") or run_dir.name)
    poisson_dir = run_dir / "poisson"
    match_rows = _read_csv_rows(poisson_dir / "poisson_match_summary.csv")
    if not match_rows:
        return None

    board_path = output_dir / "projection_checkpoints" / run_date / "index.html"
    board_path.parent.mkdir(parents=True, exist_ok=True)
    one_x_two = _single_by_match(_read_csv_rows(poisson_dir / "poisson_1x2.csv"))
    totals = _lookup_by_match(_read_csv_rows(poisson_dir / "poisson_totals.csv"))
    btts = _single_by_match(_read_csv_rows(poisson_dir / "poisson_btts.csv"))
    clean = _single_by_match(_read_csv_rows(poisson_dir / "poisson_clean_sheets.csv"))
    scores = _lookup_by_match(_read_csv_rows(poisson_dir / "poisson_correct_score_matrix.csv"))

    real = int(entry.get("real_rows_reviewed") or 0)
    manual = int(entry.get("manual_rows_reviewed") or 0)
    sample = int(entry.get("sample_rows_reviewed") or 0)
    banners: list[str] = []
    if sample:
        banners.append("<div class=\"notice warning\"><strong>Sample/demo rows are not real current matchups.</strong></div>")
    if manual:
        banners.append("<div class=\"notice warning\"><strong>Manual rows are user supplied and not source-verified.</strong></div>")
    if real:
        banners.append("<div class=\"notice\"><strong>Real rows:</strong> review source and reliability labels before using the output.</div>")

    sections = [
        "<!doctype html><html><head><meta charset=\"utf-8\">",
        f"<title>Poisson Probability Board {escape_html(run_date)}</title>",
        f"<style>{CSS}</style></head><body>",
        f"<header><h1>Poisson Probability Board</h1><p>{escape_html(run_date)} | Probability output from generated projection checkpoint files.</p></header><main>",
        "<div class=\"notice\"><strong>Source of truth:</strong> this page reads generated CSV/Markdown artifacts only. It does not recompute projections or add data sources.</div>",
        "<div class=\"notice\"><strong>Guardrails:</strong> review-only probability output, no current StatsBomb, proxy adjustments disabled, and rating/manual/sample warnings remain visible.</div>",
        *banners,
        "<section class=\"grid\">",
        f"<div class=\"metric\"><span>Status</span><span class=\"{_status_class(entry.get('status'))}\">{escape_html(entry.get('status'))}</span></div>",
        f"<div class=\"metric\"><span>Rows</span>Real {real} | Manual {manual} | Sample {sample}</div>",
        f"<div class=\"metric\"><span>Matches with Poisson board</span>{escape_html(len(match_rows))}</div>",
        f"<div class=\"metric\"><span>Warning flags</span>{escape_html(entry.get('warnings_count'))}</div>",
        "</section>",
        "<h2>Raw Artifacts</h2>",
        _artifact_links(run_date),
    ]
    for row in match_rows:
        key = _match_key(row)
        sections.append(_match_card(
            row,
            one_x_two.get(key, {}),
            totals.get(key, []),
            btts.get(key, {}),
            clean.get(key, {}),
            scores.get(key, []),
        ))
    sections.extend(["</main></body></html>"])
    board_path.write_text("\n".join(sections), encoding="utf-8")
    return str(board_path)


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
            run_dir / "projection_checkpoint_summary.md",
            run_dir / "poisson" / "poisson_summary.md",
            run_dir / "current_international_source_summary.md",
            run_dir / "current_international_projection_report.md",
            run_dir / "fixture_readiness" / "fixture_readiness_summary.md",
            run_dir / "source_audit" / "source_audit_summary.md",
            run_dir / "cache_seed" / "cache_seed_summary.md",
        ] if path.exists()
    ]
    safety = scan_report_safety(markdown_paths)
    sections = [
        "<!doctype html><html><head><meta charset=\"utf-8\">",
        f"<title>Run {escape_html(run_id)}</title>",
        f"<style>{CSS}</style></head><body>",
        f"<header><h1>{escape_html(entry.get('entry_type') or 'Run')} {escape_html(run_id)}</h1><p>Run date {escape_html(entry.get('run_date'))} | Generated {escape_html(entry.get('generated_at'))}</p></header><main>",
        "<div class=\"notice\"><strong>Guardrail:</strong> This viewer reads generated outputs only. It does not recompute projections, create betting recommendations, or claim proxy metrics are true event/tracking style.</div>",
        "<div class=\"notice\"><strong>Interpretation:</strong> probability and support fields are Data Support / Risk Context, not certainty and not a recommendation.</div>",
        "<section class=\"grid\">",
        f"<div class=\"metric\"><span>Status</span><span class=\"{_status_class(entry.get('status'))}\">{escape_html(entry.get('status'))}</span></div>",
        f"<div class=\"metric\"><span>Currentness</span><span class=\"{_status_class(entry.get('currentness_status'))}\">{escape_html(entry.get('currentness_status'))}</span></div>",
        f"<div class=\"metric\"><span>Season sanity</span><span class=\"{_status_class(entry.get('season_sanity_status'))}\">{escape_html(entry.get('season_sanity_status'))}</span></div>",
        f"<div class=\"metric\"><span>Rows</span>{escape_html(entry.get('row_count'))}</div>",
        f"<div class=\"metric\"><span>Resolved / unresolved</span>{escape_html(entry.get('resolved_rows') or '')} / {escape_html(entry.get('unresolved_rows') or '')}</div>",
        f"<div class=\"metric\"><span>Projected / skipped placeholders</span>{escape_html(entry.get('projected_rows') or '')} / {escape_html(entry.get('skipped_placeholder_rows') or '')}</div>",
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
    if entry.get("entry_type") == "projection_checkpoint" and int(entry.get("poisson_match_count") or 0) > 0:
        run_date = str(entry.get("run_date") or run_dir.name)
        sections.append(
            "<div class=\"notice\">"
            f"<strong>Probability board:</strong> <a class=\"board-link\" href=\"../projection_checkpoints/{escape_html(run_date)}/index.html\">"
            "Open readable Poisson probability board</a>"
            "</div>"
        )
    if int(entry.get("skipped_placeholder_rows") or 0) > 0:
        sections.append(
            "<div class=\"notice warning\"><strong>Unresolved placeholder fixtures were skipped and not projected.</strong> "
            "<a href=\"#fixture-readiness\">Open fixture readiness outputs below.</a></div>"
        )
    for title, filename in [
        ("Club Slate", "club_slate_projections.csv"),
        ("International Slate", "international_slate_projections.csv"),
        ("Profile Comparison", "projection_profile_comparison.csv"),
        ("Projection Checkpoint Rows", "projection_checkpoint_rows.csv"),
        ("Projection Checkpoint Flags", "projection_checkpoint_flags.csv"),
        ("Current International Slate", "current_international_slate.csv"),
        ("Current International Projections", "current_international_projections.csv"),
        ("Source Audit", "source_audit/source_audit.csv"),
        ("Fixture Coverage", "source_audit/fixture_coverage.csv"),
        ("Rating Coverage", "source_audit/rating_coverage.csv"),
        ("Stat Coverage", "source_audit/stat_coverage.csv"),
        ("Match Data Coverage", "source_audit/match_data_coverage.csv"),
        ("Resolved Fixtures", "fixture_readiness/resolved_fixtures.csv"),
        ("Unresolved Fixtures", "fixture_readiness/unresolved_fixtures.csv"),
        ("Projection Eligible Fixtures", "fixture_readiness/projection_eligible_fixtures.csv"),
        ("Projection Skipped Fixtures", "fixture_readiness/projection_skipped_fixtures.csv"),
        ("Fixture Seed Results", "cache_seed/fixture_seed_results.csv"),
        ("Rating Seed Results", "cache_seed/rating_seed_results.csv"),
        ("Stat Seed Results", "cache_seed/stat_seed_results.csv"),
        ("Source Fetch Results", "cache_seed/source_fetch_results.csv"),
        ("Rating Parse Diagnostics", "cache_seed/rating_parse_diagnostics.csv"),
        ("Parsed Fixture Rows", "cache_seed/parsed_fixture_rows.csv"),
        ("Parsed Rating Rows", "cache_seed/parsed_rating_rows.csv"),
        ("Parsed Stat Rows", "cache_seed/parsed_stat_rows.csv"),
        ("Poisson Match Summary", "poisson/poisson_match_summary.csv"),
        ("Poisson Correct Score Matrix", "poisson/poisson_correct_score_matrix.csv"),
    ]:
        path = run_dir / filename
        if path.exists():
            heading_id = " id=\"fixture-readiness\"" if title == "Resolved Fixtures" else ""
            sections.append(f"<h2{heading_id}>{escape_html(title)}</h2>")
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
    for header in [
        "date",
        "type",
        "status",
        "currentness",
        "season",
        "rows",
        "real",
        "manual",
        "sample",
        "resolved",
        "unresolved",
        "skipped placeholders",
        "poisson matches",
        "warnings",
        "slate_type",
        "detail",
        "probability board",
    ]:
        rows.append(f"<th>{escape_html(header)}</th>")
    rows.append("</tr></thead><tbody>")
    for entry in entries:
        run_id = str(entry.get("run_id") or entry.get("run_date"))
        run_date = str(entry.get("run_date") or "")
        poisson_match_count = int(entry.get("poisson_match_count") or 0)
        board_link = (
            f"<a class=\"board-link\" href=\"projection_checkpoints/{escape_html(run_date)}/index.html\">Open</a>"
            if entry.get("entry_type") == "projection_checkpoint" and poisson_match_count > 0
            else "<span class=\"muted\">None</span>"
        )
        cls = " class=\"latest\"" if run_id == latest_run_id else ""
        rows.append(f"<tr{cls}>")
        rows.append(f"<td>{escape_html(run_date)}</td>")
        rows.append(f"<td>{escape_html(entry.get('entry_type') or 'daily_run')}</td>")
        rows.append(f"<td><span class=\"{_status_class(entry.get('status'))}\">{escape_html(entry.get('status'))}</span></td>")
        rows.append(f"<td><span class=\"{_status_class(entry.get('currentness_status'))}\">{escape_html(entry.get('currentness_status'))}</span></td>")
        rows.append(f"<td>{escape_html(entry.get('season_sanity_status'))}</td>")
        rows.append(f"<td>{escape_html(entry.get('row_count'))}</td>")
        rows.append(f"<td>{escape_html(entry.get('real_rows_reviewed') or '')}</td>")
        rows.append(f"<td>{escape_html(entry.get('manual_rows_reviewed') or '')}</td>")
        rows.append(f"<td>{escape_html(entry.get('sample_rows_reviewed') or '')}</td>")
        rows.append(f"<td>{escape_html(entry.get('resolved_rows') or '')}</td>")
        rows.append(f"<td>{escape_html(entry.get('unresolved_rows') or '')}</td>")
        rows.append(f"<td>{escape_html(entry.get('skipped_placeholder_rows') or '')}</td>")
        rows.append(f"<td>{escape_html(poisson_match_count or '')}</td>")
        rows.append(f"<td>{escape_html(entry.get('warnings_count'))}</td>")
        rows.append(f"<td>{escape_html(entry.get('slate_type'))}</td>")
        rows.append(f"<td><a href=\"runs/{escape_html(run_id)}.html\">Open</a></td>")
        rows.append(f"<td>{board_link}</td>")
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
    poisson_board_pages: list[str] = []
    safety_warnings: list[str] = []
    for entry in entries:
        page, safety = _run_detail_page(entry, output)
        detail_pages.append(page)
        safety_warnings.extend(safety["safety_warnings"])
        if entry.get("entry_type") == "projection_checkpoint":
            board_page = _projection_checkpoint_board_page(entry, output)
            if board_page:
                poisson_board_pages.append(board_page)
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
        "poisson_board_pages": poisson_board_pages,
        "safety_scan_status": status,
        "safety_warnings": safety_warnings,
    }
