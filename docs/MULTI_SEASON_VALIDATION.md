# Multi-Season Validation

Phase 14 validates projection profiles across multiple Football-Data leagues and seasons before adding richer UI or visual work.

One season is not enough because a profile can look useful in a single schedule, league scoring environment, or market shape and then fail when the sample changes. The validator keeps league and season boundaries explicit, evaluates only prior rows inside each league-season group, and reports W/D/L, goals, calibration, disagreement, and confidence-bucket metrics.

Generated inputs and reports remain reproducible artifacts:

```powershell
.\.venv\Scripts\python.exe -m src.cli download-football-data-seasons --season-codes 2526,2425,2324,2223,2122 --leagues E0,E1,SP1,D1,I1,F1 --output-dir data/raw/football-data
.\.venv\Scripts\python.exe -m src.cli normalize-multi-season-football-data --input data/raw/football-data --output data/processed/multi_season_match_results.csv
.\.venv\Scripts\python.exe -m src.cli validate-multi-season-profiles --input data/processed/multi_season_match_results.csv --start-date 2021-08-01 --end-date 2026-05-31 --monthly --by-league --by-season
```

This is not a betting system. The outputs compare model profiles and calibration behavior, not picks. Proxy style remains `free_proxy_style`, and proxy score adjustments remain disabled by default.
