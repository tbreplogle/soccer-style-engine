# Developer Commands

## Tests

Quick tests:

```powershell
.\scripts\test_quick.ps1
```

Full tests:

```powershell
.\scripts\test_full.ps1
```

Direct pytest commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest -m quick
```

## Daily Run

```powershell
.\scripts\run_today.ps1
```

Useful options:

```powershell
.\scripts\run_today.ps1 -AsOfDate 2026-05-25 -SkipDownload -MaxMatches 5
.\scripts\run_today.ps1 -Download
```

## Viewer

```powershell
.\scripts\build_viewer.ps1
.\scripts\open_viewer.ps1
```

## Health Check

```powershell
.\.venv\Scripts\python.exe -m src.cli operational-health-check
```

The health check stays fast and checks scripts, docs, CLI command registration, and generated-output ignore rules.
