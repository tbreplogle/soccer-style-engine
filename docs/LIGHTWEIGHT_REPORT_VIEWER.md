# Lightweight Report Viewer

Phase 18 adds a small local static viewer for generated run outputs.

The viewer reads files already written by the daily pipeline under:

```text
outputs/runs/YYYY-MM-DD/
```

It writes static HTML to:

```text
outputs/viewer/index.html
outputs/viewer/runs/<run_id>.html
outputs/viewer/projection_checkpoints/YYYY-MM-DD/index.html
```

Generated viewer files are ignored by git.

## What It Does

- Lists available run folders.
- Reads `run_manifest.json` and `run_summary.md`.
- Shows currentness, season sanity, warnings, row counts, and slate type.
- Renders club slate, international slate, and profile comparison CSV files when present.
- Renders generated report markdown with a lightweight safe formatter.
- Renders projection checkpoint Poisson outputs as readable probability board pages when those generated files exist.
- Runs a warning-only safety scan for action-language terms in generated reports.

## What It Does Not Do

- It does not recompute projections.
- It does not call model or agent code.
- It does not download data.
- It does not create betting picks or wagering advice.
- It does not re-enable proxy score adjustments.
- It does not claim free proxy metrics are true event/tracking style.
- It is not the future dashboard, PassSonar, heat map, style fingerprint, or event-visual layer.

The source of truth remains the daily runner outputs and run manifests.

## Commands

List runs:

```powershell
.\.venv\Scripts\python.exe -m src.cli list-runs --runs-root outputs/runs
```

List runs as JSON:

```powershell
.\.venv\Scripts\python.exe -m src.cli list-runs --runs-root outputs/runs --json
```

Build the viewer:

```powershell
.\.venv\Scripts\python.exe -m src.cli build-report-viewer --runs-root outputs/runs --output-dir outputs/viewer
```

Print the local file path to open:

```powershell
.\.venv\Scripts\python.exe -m src.cli open-report-viewer --viewer outputs/viewer/index.html
```

Build the viewer from a daily pipeline run:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --skip-download --build-viewer
```

## Safety Scan

The safety scan reports warnings for risky action-language terms such as `bet`, `take`, `play`, `lock`, `pick`, and `wager`.

Normal guardrail text such as "no betting recommendation" is allowed. The scan does not delete or rewrite generated reports.

