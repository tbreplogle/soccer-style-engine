# Soccer Style Engine

Version: `0.1.0-free-v1`

Soccer Style Engine is a local, explainable soccer projection workflow. It tracks measurable team behavior, validates model behavior, writes operational run outputs, and renders those outputs in a lightweight static viewer.

The project rule remains:

> We track measurable team behavior first, then use that evidence to explain projections.

## What It Can Do Today

- Normalize free Football-Data CSVs and sample/open event data.
- Build conservative club and international projection reports.
- Run currentness, season sanity, leakage, calibration, and validation checks.
- Write daily run manifests, summaries, logs, projections, and reports.
- Build a static local report viewer from generated run outputs.
- Review projection outputs with a local checkpoint before treating them as ready.
- Build a Poisson probability board from projected team xG for projection review.
- Open readable Poisson board pages from the static viewer for checkpoint runs.
- Audit current international fixture/rating/stat source coverage from local public-source caches.
- Seed current international source caches from public no-login/no-key connectors.
- Keep no-betting guardrails active by default.

## What It Does Not Do Yet

- No betting recommendations or wagering advice.
- No frontend dashboard, PassSonar, heat maps, style fingerprints, or event visuals.
- No paid data dependencies or fragile scraping.
- No claim that current free proxy metrics are true event/tracking style.
- No mixing club ratings into international-team projections.

## Daily Workflow

Quickest path:

```powershell
.\scripts\run_today.ps1
```

Or use the friendly CLI wrapper:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-today --as-of-date 2026-05-25 --skip-download --max-matches 5
```

This writes a dated run under `outputs/runs/`, updates run logs under `outputs/run_logs/`, and builds the static viewer at `outputs/viewer/index.html`.

Open the viewer path printed at the end, or run:

```powershell
.\scripts\open_viewer.ps1
```

## Local-Only Runs

Use `--skip-download` when you want to run from existing local CSVs only:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-today --as-of-date 2026-05-25 --skip-download --max-matches 5
```

The PowerShell workflow script uses local cached data by default. Use `.\scripts\run_today.ps1 -Download` when a data refresh is intentional.

## International Data

International workflows are available when local international data is supplied:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --include-international --international-input data/processed/international_match_results.csv --skip-download --build-viewer
```

International projections remain sparse/historical unless current international data is supplied. Club and international ratings stay separate.

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

Final v1 validation:

```powershell
.\.venv\Scripts\python.exe -m src.cli validate-v1
.\scripts\validate_v1.ps1
```

## Data Modes

Current free data from Football-Data is match-level data. It supports baseline projections and free proxy context, but it is not true event/tracking style.

Historical StatsBomb Open Data is event-level sample/open data. It can support event-style metrics where the event fields exist. If tracking or 360 data is missing, the engine must not fake it.

## Generated Outputs

Generated outputs are ignored and should not be committed:

- `outputs/runs/`
- `outputs/run_logs/`
- `outputs/viewer/`
- `outputs/projection_checkpoints/`
- `outputs/reports/`
- `outputs/projections/`
- `data/processed/`
- raw Football-Data and StatsBomb folders

Commit source, tests, docs, scripts, examples, and sample input fixtures.

## Release Docs

- `docs/V1_RELEASE_NOTES.md`
- `docs/V1_LIMITATIONS.md`
- `docs/V1_RUN_CHECKLIST.md`
- `docs/POISSON_BOARD_VIEWER.md`
- `docs/CURRENT_INTERNATIONAL_SOURCE_HARVEST.md`
- `docs/CURRENT_INTERNATIONAL_CACHE_SEEDING.md`

## Roadmap

After free v1, the natural next work is better calibration, faster full validation, reliable roster/injury inputs if a trustworthy source exists, and eventually style visuals. PassSonar, heat maps, style fingerprints, dashboards, and event visuals are intentionally deferred.
