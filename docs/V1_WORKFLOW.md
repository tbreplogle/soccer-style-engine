# V1 Workflow

The v1 workflow is meant to be repeatable from a clean terminal.

## Normal Daily Run

```powershell
.\scripts\run_today.ps1
```

This runs:

- operational health check
- daily pipeline with operational defaults using local cached data by default
- processed-data reuse when fresh
- static viewer generation

The script prints the viewer path at the end.

Use `.\scripts\run_today.ps1 -Download` when you intentionally want the script to refresh Football-Data inputs.

## Friendly CLI Equivalent

```powershell
.\.venv\Scripts\python.exe -m src.cli run-today --as-of-date 2026-05-25 --skip-download --max-matches 5
```

`run-today` is a wrapper around `run-daily-pipeline`. It keeps currentness policy at `warn`, builds the viewer, reuses fresh processed data, and skips profile comparison unless `--run-profile-comparison` is supplied.

## Open The Viewer

```powershell
.\scripts\open_viewer.ps1
```

The viewer reads generated run outputs. It does not recompute projections.

## Guardrails

No betting recommendations are produced. Market gaps are diagnostics only. Data Support / Risk Context is review context, not certainty.

Style visuals remain deferred until the operational output is stable.
