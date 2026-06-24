# Phase 14 Usage

Phase 14 hardens calibration before frontend work, betting workflows, PassSonar, heat maps, style fingerprints, or event visuals.

## Full Club Flow

```powershell
.\.venv\Scripts\python.exe -m src.cli download-football-data-seasons --season-codes 2526,2425,2324,2223,2122 --leagues E0,E1,SP1,D1,I1,F1 --output-dir data/raw/football-data
.\.venv\Scripts\python.exe -m src.cli normalize-multi-season-football-data --input data/raw/football-data --output data/processed/multi_season_match_results.csv
.\.venv\Scripts\python.exe -m src.cli validate-multi-season-profiles --input data/processed/multi_season_match_results.csv --start-date 2021-08-01 --end-date 2026-05-31 --monthly --by-league --by-season
.\.venv\Scripts\python.exe -m src.cli run-holdout-validation --input data/processed/multi_season_match_results.csv --train-seasons 2122,2223,2324 --validation-season 2425 --test-season 2526
.\.venv\Scripts\python.exe -m src.cli harden-confidence --input data/processed/multi_season_match_results.csv --start-date 2021-08-01 --end-date 2026-05-31
.\.venv\Scripts\python.exe -m src.cli audit-leakage --input data/processed/multi_season_match_results.csv --start-date 2021-08-01 --end-date 2026-05-31
```

## International Sanity Check

```powershell
.\.venv\Scripts\python.exe -m src.cli validate-international --statsbomb-root data/raw/statsbomb-open-data/data --competition-name "FIFA World Cup" --season-id 106 --max-matches 64 --output-dir outputs/reports
```

This command should not fail when local StatsBomb data is missing. International reports keep club and national-team ratings separate, preserve neutral-site context, and label historical event data as historical.

Raw data, processed multi-season CSVs, projections, and generated reports remain ignored. Committed files should be source, tests, docs, and small examples only.
