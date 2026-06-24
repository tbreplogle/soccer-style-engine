from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Iterable


def escape_html(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def markdown_to_html(markdown: str) -> str:
    """Render a small safe markdown subset used by generated reports."""
    lines = markdown.splitlines()
    output: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            output.append("</ul>")
            in_list = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                output.append("<pre><code>" + escape_html("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                close_list()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            close_list()
            continue
        if stripped.startswith("#"):
            close_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 4)
            text = stripped[level:].strip()
            output.append(f"<h{level}>{escape_html(text)}</h{level}>")
            continue
        if stripped.startswith("- "):
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{escape_html(stripped[2:].strip())}</li>")
            continue
        close_list()
        output.append(f"<p>{escape_html(stripped)}</p>")
    close_list()
    if in_code:
        output.append("<pre><code>" + escape_html("\n".join(code_lines)) + "</code></pre>")
    return "\n".join(output)


def csv_to_html_table(path: str | Path, max_rows: int = 50) -> str:
    target = Path(path)
    if not target.exists():
        return ""
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) >= max_rows:
                break
    if not fieldnames:
        return "<p class=\"muted\">CSV file is empty or missing headers.</p>"
    parts = ["<div class=\"table-wrap\"><table>", "<thead><tr>"]
    parts.extend(f"<th>{escape_html(field)}</th>" for field in fieldnames)
    parts.extend(["</tr></thead>", "<tbody>"])
    for row in rows:
        parts.append("<tr>")
        parts.extend(f"<td>{escape_html(row.get(field, ''))}</td>" for field in fieldnames)
        parts.append("</tr>")
    if not rows:
        parts.append(f"<tr><td colspan=\"{len(fieldnames)}\" class=\"muted\">No rows found.</td></tr>")
    parts.extend(["</tbody>", "</table></div>"])
    return "\n".join(parts)


def unordered_list(items: Iterable[object]) -> str:
    values = [f"<li>{escape_html(item)}</li>" for item in items if str(item)]
    if not values:
        return "<p class=\"muted\">None</p>"
    return "<ul>" + "".join(values) + "</ul>"
