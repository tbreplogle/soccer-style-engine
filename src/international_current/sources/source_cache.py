from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def parsed_dir(cache_dir: str | Path) -> Path:
    path = Path(cache_dir) / "parsed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def raw_dir(cache_dir: str | Path) -> Path:
    path = Path(cache_dir) / "raw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_parsed_cache(frame: pd.DataFrame, cache_dir: str | Path, name: str, metadata: dict[str, Any] | None = None) -> Path:
    path = parsed_dir(cache_dir) / f"{name}.csv"
    frame.to_csv(path, index=False)
    meta = {
        "cache_name": name,
        "written_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(frame),
        **(metadata or {}),
    }
    path.with_suffix(".metadata.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return path


def mirror_root_cache(frame: pd.DataFrame, cache_dir: str | Path, name: str) -> Path:
    path = Path(cache_dir) / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path
