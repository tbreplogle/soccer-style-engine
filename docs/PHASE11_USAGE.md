# Phase 11 Usage

## Download Multi-League CSVs

```powershell
.\.venv\Scripts\python.exe -m src.cli download-football-data-leagues --season-code 2526 --fallback-season-code 2425 --leagues E0,E1,SP1,D1,I1,F1 --output-dir data/raw/football-data
```

Downloads are best-effort by league. A failed league does not fail the whole batch.

## Normalize Multi-League Data

```powershell
.\.venv\Scripts\python.exe -m src.cli normalize-multi-league-football-data --input data/raw/football-data --output data/processed/multi_league_current_match_results.csv --season 2025-2026
```

The normalized file is generated output and remains ignored.

## Diagnose Profiles Across Leagues

```powershell
.\.venv\Scripts\python.exe -m src.cli diagnose-multi-league-profiles --input data/processed/multi_league_current_match_results.csv --start-date 2025-10-01 --end-date 2026-05-24 --monthly
```

This runs each projection profile by league. It also writes a confidence calibration report.

## Audit International Readiness

```powershell
.\.venv\Scripts\python.exe -m src.cli audit-international-readiness --statsbomb-root data/raw/statsbomb-open-data/data --output-dir outputs/reports
```

If local StatsBomb Open Data is missing, the command reports that state and still writes an audit report.

