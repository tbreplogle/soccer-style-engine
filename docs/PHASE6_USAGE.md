# Phase 6 Usage

## Normalize Local Football-Data CSVs

```powershell
.\.venv\Scripts\python.exe -m src.cli normalize-football-data --input data/raw/football-data --output data/processed/current_match_results.csv --league EPL --season 2025-2026
```

## Build Free Style Proxies

```powershell
.\.venv\Scripts\python.exe -m src.cli build-free-proxies --input data/processed/current_match_results.csv --as-of-date YYYY-MM-DD
```

## Project a Current Match

```powershell
.\.venv\Scripts\python.exe -m src.cli project-current --input data/processed/current_match_results.csv --home "Team A" --away "Team B" --as-of-date YYYY-MM-DD
```

## Backtest the Free Current Model

```powershell
.\.venv\Scripts\python.exe -m src.cli backtest-current --input data/processed/current_match_results.csv --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

## Interpretation

Confidence is lower when either team has fewer than 6 prior matches or when shots, corners, SOT, or odds are missing. `free_proxy_style` means the model is using match-stat proxies, not true event/tracking style. Do not treat proxy outputs as real possession, movement, pace, or defensive-shape claims.
