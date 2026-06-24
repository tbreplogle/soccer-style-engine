# Data Currentness

Phase 16 checks whether Football-Data inputs are present, plausible, fresh enough, and safe to use.

The currentness check inspects raw CSVs and processed data:

```powershell
.\.venv\Scripts\python.exe -m src.cli check-data-currentness --raw-dir data/raw/football-data --processed data/processed/multi_league_current_match_results.csv --as-of-date 2026-05-25 --season-code 2526 --leagues E0,E1,SP1,D1,I1,F1
```

Statuses:

- `current`: raw and processed data look usable.
- `probably_current`: usable with caveats, often historical or offseason context.
- `stale`: latest completed match is too far behind the run date during an active season.
- `missing`: required raw league files are missing.
- `unsafe`: no completed matches, bad date structure, or required columns missing.

Currentness does not make projections more certain. It only tells the runner whether the data surface is fresh enough to trust for the chosen mode.
