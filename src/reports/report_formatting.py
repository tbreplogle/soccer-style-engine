from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


NO_BETTING_DISCLAIMER = "These projections are model context only and are not betting recommendations."


def split_csv_arg(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def write_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return output


def markdown_table(frame: pd.DataFrame, columns: Iterable[str], max_rows: int = 20) -> str:
    cols = [col for col in columns if col in frame.columns]
    if frame.empty or not cols:
        return "_No rows._"
    shown = frame[cols].head(max_rows)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in shown.iterrows():
        values = []
        for col in cols:
            value = row[col]
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            elif pd.isna(value):
                values.append("")
            else:
                values.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_markdown_report(
    path: str | Path,
    title: str,
    data_source: str,
    slate_type: str,
    frame: pd.DataFrame,
    summary_columns: list[str],
    detail_columns: list[str],
    matchup_columns: tuple[str, str],
    extra_notes: list[str] | None = None,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {title}",
        "",
        f"Date generated: {pd.Timestamp.now('UTC').strftime('%Y-%m-%d %H:%M UTC')}",
        f"Data source: `{data_source}`",
        f"Slate type: `{slate_type}`",
        "",
        "## Model Guardrails",
        "",
        f"- {NO_BETTING_DISCLAIMER}",
        "- Proxy style context is not true tracking or event style unless explicitly labeled as event data.",
        "- Generated reports and projection CSVs are reproducible outputs.",
        "",
        "## Summary",
        "",
        markdown_table(frame, summary_columns),
        "",
        "## Matchup Details",
        "",
    ]
    left, right = matchup_columns
    if frame.empty:
        lines.append("_No projected matchups._")
    else:
        for key, group in frame.groupby([left, right], dropna=False):
            lines.extend([f"### {key[0]} vs {key[1]}", "", markdown_table(group, detail_columns), ""])
    lines.extend([
        "## Confidence And Risk",
        "",
        "Confidence is an evidence-quality signal, not certainty. Risk flags identify sparse samples, missing data, neutral-site uncertainty, or profile disagreement.",
        "",
    ])
    if extra_notes:
        lines.extend(["## Notes", ""])
        lines.extend([f"- {note}" for note in extra_notes])
        lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
