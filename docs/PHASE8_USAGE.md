# Phase 8 Usage

Run diagnostics on normalized Football-Data-style current results:

```powershell
.\.venv\Scripts\python.exe -m src.cli diagnose-proxies --input data/processed/current_match_results.csv --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

Optional:

```powershell
.\.venv\Scripts\python.exe -m src.cli diagnose-proxies --input data/processed/current_match_results.csv --start-date YYYY-MM-DD --end-date YYYY-MM-DD --caps 0,0.03,0.05,0.08,0.12,0.20 --min-matches 6 --output-dir outputs/reports
```

Add `--include-window-breakdowns` to include monthly and rolling 30-day windows. The default CLI run evaluates the requested custom window so real-season diagnostics finish quickly enough for routine smoke tests.

Generated files are ignored:

- `outputs/reports/proxy_diagnostics_summary.md`
- `outputs/reports/proxy_diagnostics_results.csv`

To explicitly allow current projections to move xG with proxy adjustments:

```powershell
.\.venv\Scripts\python.exe -m src.cli project-current --input data/processed/current_match_results.csv --home "Team A" --away "Team B" --as-of-date YYYY-MM-DD --enable-proxy-adjustments --proxy-cap 0.05
```

Use this only after diagnostics support it. Without those flags, proxy explanations can appear, but score adjustments stay disabled by default.
