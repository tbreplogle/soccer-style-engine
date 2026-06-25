# Phase 26 Poisson Board Viewer Example

Build a checkpoint and static viewer:

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --run-current-international --no-network --allow-sample-data --build-viewer --build-poisson-board
```

Open:

```text
outputs/viewer/index.html
```

The main viewer index lists daily runs and projection checkpoint runs. For checkpoint rows with Poisson output, use the probability board link to open:

```text
outputs/viewer/projection_checkpoints/YYYY-MM-DD/index.html
```

The page reads generated checkpoint files only. It does not download data, recompute projections, use current StatsBomb, or enable proxy adjustments.
