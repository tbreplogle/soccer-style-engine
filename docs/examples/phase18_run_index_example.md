# Phase 18 Run Index Example

Example command:

```powershell
.\.venv\Scripts\python.exe -m src.cli list-runs --runs-root outputs/runs
```

Example output:

```text
date        status                 currentness       rows  warnings  slate_type
----------  ---------------------  ----------------  ----  --------  ---------------------------
2026-05-25  success_with_warnings  season_completed  2304  6         historical_validation_slate
```

The run index is metadata only. It reads manifests and generated files from `outputs/runs/`.

