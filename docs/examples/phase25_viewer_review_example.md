# Phase 25 Viewer Review Example

Build a checkpoint and refresh the existing static viewer:

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --run-current-international --manual-matchups data/sample/current_international_matchups.csv --no-network --build-viewer --build-poisson-board
```

Then open:

```text
outputs/viewer/index.html
```

The viewer lists projection checkpoints alongside normal run outputs when built from `outputs`. A checkpoint detail page shows:

- checkpoint status
- row count
- warning count
- checkpoint rows CSV
- checkpoint flags CSV
- markdown checkpoint summary
- Poisson summary
- Poisson match summary CSV
- Poisson correct score matrix CSV

The viewer still reads generated files only. It does not recompute projections, add a data source, or make style-aware claims.
