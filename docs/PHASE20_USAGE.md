# Phase 20 Usage

Phase 20 is the final free v1 validation and release-prep checkpoint.

## Validate V1

```powershell
.\.venv\Scripts\python.exe -m src.cli validate-v1
.\scripts\validate_v1.ps1
```

The CLI validation is fast and checks release docs, scripts, guardrails, ignore rules, version, and operational health.

The script validation runs a fuller local checklist without requiring network access.

## Run The Normal Workflow

```powershell
.\.venv\Scripts\python.exe -m src.cli run-today --as-of-date 2026-05-25 --skip-download --max-matches 5
```

## Build The Viewer

```powershell
.\.venv\Scripts\python.exe -m src.cli build-report-viewer --runs-root outputs/runs --output-dir outputs/viewer
```

## Release Marker

The version marker is `0.1.0-free-v1` in `src/version.py`.

Do not create a Git tag automatically. Tag manually after review if desired.

