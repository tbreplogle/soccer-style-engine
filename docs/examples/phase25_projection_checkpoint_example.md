# Phase 25 Projection Checkpoint Example

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --run-current-international --no-network --max-matches 10
```

Expected terminal shape:

```text
Projection Results Checkpoint
Status: warning
Rows reviewed: 0 real rows, 0 manual rows, 0 sample/demo rows
Average projected total: None
Most common likely score: missing
Data support counts: {}
Style inputs available rows: 0
Warnings: 1
Output path: outputs/projection_checkpoints/2026-06-24
```

Committed sample fixtures are not used as real current games by default. For demo output, add `--allow-sample-data`; for user-supplied fixtures, pass `--manual-matchups`.
