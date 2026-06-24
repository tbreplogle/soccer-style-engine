# Phase 16 Usage

Health check:

```powershell
.\.venv\Scripts\python.exe -m src.cli operational-health-check
```

Season sanity:

```powershell
.\.venv\Scripts\python.exe -m src.cli check-season-sanity --season-code 2526 --as-of-date 2026-05-25
```

Currentness:

```powershell
.\.venv\Scripts\python.exe -m src.cli check-data-currentness --raw-dir data/raw/football-data --processed data/processed/multi_league_current_match_results.csv --as-of-date 2026-05-25 --season-code 2526 --leagues E0,E1,SP1,D1,I1,F1
```

Daily runner with warning policy:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --season-code 2526 --leagues E0,E1,SP1,D1,I1,F1 --slate-type historical --max-matches 10 --skip-download --run-quick-audit --currentness-policy warn
```

Policies:

- `warn`: continue and mark warnings.
- `fail-on-missing`: fail when required raw files are missing.
- `fail-on-stale`: fail on stale, missing, or unsafe data.
- `fail-on-unsafe`: fail only on unsafe data.

Run outputs go to `outputs/runs/YYYY-MM-DD/`; run logs go to `outputs/run_logs/`. Both are ignored.
