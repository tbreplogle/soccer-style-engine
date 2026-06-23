from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd


def write_projection_csv(projections: pd.DataFrame, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    projections.to_csv(output, index=False)


def write_markdown_report(title: str, sections: Mapping[str, str], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]
    for heading, body in sections.items():
        lines.extend([f"## {heading}", "", str(body), ""])
    output.write_text("\n".join(lines), encoding="utf-8")
