# Phase 12 Usage

## List International Competitions

```powershell
.\.venv\Scripts\python.exe -m src.cli list-international-competitions --statsbomb-root data/raw/statsbomb-open-data/data
```

## Build International Dataset

```powershell
.\.venv\Scripts\python.exe -m src.cli build-international-dataset --statsbomb-root data/raw/statsbomb-open-data/data --competition-name "FIFA World Cup" --season-id 106 --max-matches 20 --output data/processed/international_match_results.csv
```

The generated dataset stays ignored.

## Project International Match

```powershell
.\.venv\Scripts\python.exe -m src.cli project-international --input data/processed/international_match_results.csv --team-a "Brazil" --team-b "Morocco" --as-of-date 2022-12-01 --neutral-site true
```

## Backtest International

```powershell
.\.venv\Scripts\python.exe -m src.cli backtest-international --input data/processed/international_match_results.csv --start-date 2022-11-25 --end-date 2022-12-18 --min-prior-matches 2
```

Outputs are limited foundation reports. They are projection context, not picks.

