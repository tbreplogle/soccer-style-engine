# Phase 19 Usage

Phase 19 polishes the v1 workflow and makes daily development faster.

## Quick Test

```powershell
.\scripts\test_quick.ps1
```

## Full Test

```powershell
.\scripts\test_full.ps1
```

## One-Command Daily Workflow

```powershell
.\scripts\run_today.ps1
```

The script runs the health check, runs the daily pipeline, reuses fresh processed data, builds the viewer, and prints the viewer path.

For speed, the script uses local cached Football-Data by default. Add `-Download` when refreshing raw files is intentional.

## Friendly CLI

```powershell
.\.venv\Scripts\python.exe -m src.cli run-today --as-of-date 2026-05-25 --skip-download --max-matches 5
```

Options include:

- `--as-of-date`
- `--leagues`
- `--skip-download`
- `--max-matches`
- `--include-international`
- `--open-viewer`
- `--run-profile-comparison`

## Why No Full Dashboard Yet

The static viewer is a reader for generated outputs. It is not a second projection engine and not the final UI. PassSonar, heat maps, style fingerprints, dashboards, and event visuals are still deferred.

## Data Limits

Current free Football-Data is match-level data. It can support baseline and free-proxy context, but it is not tracking/event style.

Historical StatsBomb Open Data can support event-style analysis where the event data exists. Missing tracking or 360 fields should stay missing.
