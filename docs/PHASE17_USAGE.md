# Phase 17 Usage

Explain currentness:

```powershell
.\.venv\Scripts\python.exe -m src.cli explain-currentness
```

Refined currentness check:

```powershell
.\.venv\Scripts\python.exe -m src.cli check-data-currentness --raw-dir data/raw/football-data --processed data/processed/multi_league_current_match_results.csv --as-of-date 2026-05-25 --season-code 2526 --leagues E0,E1,SP1,D1,I1,F1 --slate-type historical
```

Faster daily smoke:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --season-code 2526 --leagues E0,E1,SP1,D1,I1,F1 --slate-type historical --max-matches 10 --skip-download --run-quick-audit --currentness-policy warn --skip-profile-comparison --reuse-processed-if-fresh
```

Strict unsafe-only smoke:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --season-code 2526 --leagues E0,E1,SP1,D1,I1,F1 --slate-type historical --max-matches 10 --skip-download --currentness-policy fail-on-unsafe --skip-profile-comparison --reuse-processed-if-fresh
```

No UI, betting workflow, PassSonar, heat maps, dashboards, or event visuals are added in this phase.
