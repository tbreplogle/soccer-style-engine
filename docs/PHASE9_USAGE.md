# Phase 9 Usage

Run baseline diagnostics:

```powershell
.\.venv\Scripts\python.exe -m src.cli diagnose-baselines --input data/processed/current_match_results.csv --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

Optional:

```powershell
.\.venv\Scripts\python.exe -m src.cli diagnose-baselines --input data/processed/current_match_results.csv --start-date YYYY-MM-DD --end-date YYYY-MM-DD --monthly --baseline-modes goals,shots,market,totals_market,blended
```

Project with a specific baseline:

```powershell
.\.venv\Scripts\python.exe -m src.cli project-current --input data/processed/current_match_results.csv --home "Team A" --away "Team B" --as-of-date YYYY-MM-DD --baseline-mode blended
```

Proxy score adjustments stay off unless explicitly enabled. Proxy explanations can remain useful context, but the baseline carries current free projections.
