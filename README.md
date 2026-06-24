# Soccer Style Engine

Soccer Style Engine is a local, explainable soccer projection workflow. It tracks how teams play, validates model behavior, writes operational run outputs, and renders those outputs in a lightweight static viewer.

The project rule remains:

> We track measurable team behavior first, then use that evidence to explain projections.

## What It Can Do Today

- Normalize free Football-Data CSVs and sample/open event data.
- Build conservative club and international projection reports.
- Run currentness, season sanity, leakage, calibration, and validation checks.
- Write daily run manifests, summaries, logs, projections, and reports.
- Build a static local report viewer from generated run outputs.
- Keep no-betting guardrails active by default.

## What It Does Not Do Yet

- No betting recommendations or wagering advice.
- No frontend dashboard, PassSonar, heat maps, style fingerprints, or event visuals.
- No paid data dependencies or fragile scraping.
- No claim that current free proxy metrics are true event/tracking style.
- No mixing club ratings into international-team projections.

## Daily Workflow

Run the one-command local workflow:

```powershell
.\scripts\run_today.ps1
```

Or use the friendly CLI wrapper:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-today --as-of-date 2026-05-25 --skip-download --max-matches 5
```

Open the viewer path printed at the end, or run:

```powershell
.\scripts\open_viewer.ps1
```

## Tests

Quick everyday tests:

```powershell
.\scripts\test_quick.ps1
```

Full validation before commit or merge:

```powershell
.\scripts\test_full.ps1
```

Slow tests are not bad. They are the heavier validation and workflow checks that should be run intentionally.

## Data Modes

Current free data from Football-Data is match-level data. It supports baseline projections and free proxy context, but it is not true event/tracking style.

Historical StatsBomb Open Data is event-level sample/open data. It can support event-style metrics where the event fields exist. If tracking or 360 data is missing, the engine must not fake it.

## Generated Outputs

Generated outputs are ignored and should not be committed:

- `outputs/runs/`
- `outputs/run_logs/`
- `outputs/viewer/`
- `outputs/reports/`
- `outputs/projections/`
- `data/processed/`
- raw Football-Data and StatsBomb folders

Commit source, tests, docs, scripts, examples, and sample input fixtures.
