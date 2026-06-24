from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


RUN_LOG_COLUMNS = [
    "run_id",
    "run_date",
    "generated_at",
    "status",
    "currentness_status",
    "season_sanity_status",
    "leagues",
    "row_count",
    "slate_type",
    "outputs_written",
    "warnings_count",
    "error_message",
    "duration_seconds",
]


def write_run_log(row: dict[str, Any], output_dir: str | Path = "outputs/run_logs") -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / "daily_pipeline_log.csv"
    jsonl_path = root / "daily_pipeline_log.jsonl"
    normalized = {col: row.get(col, "") for col in RUN_LOG_COLUMNS}
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RUN_LOG_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(normalized)
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, default=str) + "\n")
    return {"csv_path": csv_path, "jsonl_path": jsonl_path}
