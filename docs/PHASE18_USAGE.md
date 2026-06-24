# Phase 18 Usage

Phase 18 provides a lightweight static report viewer for operational run outputs.

It is intentionally plain: no React, no server, no database, no projection recomputation, and no new data dependencies.

## Build From Existing Runs

```powershell
.\.venv\Scripts\python.exe -m src.cli list-runs --runs-root outputs/runs
.\.venv\Scripts\python.exe -m src.cli build-report-viewer --runs-root outputs/runs --output-dir outputs/viewer
.\.venv\Scripts\python.exe -m src.cli open-report-viewer --viewer outputs/viewer/index.html
```

Open the printed `index.html` path in a browser.

## Build During Daily Pipeline

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --season-code 2526 --leagues E0,E1,SP1,D1,I1,F1 --slate-type historical --max-matches 5 --skip-download --currentness-policy warn --skip-profile-comparison --reuse-processed-if-fresh --build-viewer
```

The runner writes the viewer path into `run_manifest.json` and `run_summary.md`.

## Output Location

```text
outputs/viewer/
```

Viewer output is generated and ignored. Commit source, docs, tests, and examples only.

## Guardrails

- No betting recommendations or action language.
- Market gaps remain diagnostic context only.
- Free proxy style remains proxy context, not true tracking/event style.
- Proxy score adjustments remain disabled by default.
- Club and international ratings stay separate.
- PassSonar, heat maps, style fingerprints, dashboards, and event visuals remain deferred.

