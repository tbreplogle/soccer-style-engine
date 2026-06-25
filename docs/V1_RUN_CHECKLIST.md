# V1 Run Checklist

## Normal User Flow

```powershell
.\scripts\test_quick.ps1
.\scripts\run_today.ps1
.\scripts\build_viewer.ps1
.\scripts\open_viewer.ps1
```

## Raw CLI Equivalents

```powershell
.\.venv\Scripts\python.exe -m src.cli operational-health-check
.\.venv\Scripts\python.exe -m src.cli run-today --max-matches 20
.\.venv\Scripts\python.exe -m src.cli build-report-viewer --runs-root outputs/runs --output-dir outputs/viewer
.\.venv\Scripts\python.exe -m src.cli open-report-viewer --viewer outputs/viewer/index.html
```

## Final Validation

```powershell
.\scripts\validate_v1.ps1
.\scripts\test_full.ps1
```

## What To Check

- Health check passes or has only understood warnings.
- Quick tests pass.
- Daily workflow writes a run manifest and run summary.
- Viewer opens locally.
- Generated outputs remain ignored.
- No wagering recommendations are introduced.
- Proxy adjustments remain disabled by default.

