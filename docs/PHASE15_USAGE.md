# Phase 15 Usage

Phase 15 makes the engine operational without adding frontend work, betting picks, paid data dependencies, fragile scraping, PassSonar, heat maps, dashboards, or event visuals.

Check defaults:

```powershell
.\.venv\Scripts\python.exe -m src.cli explain-operational-defaults
```

Check operational health:

```powershell
.\.venv\Scripts\python.exe -m src.cli operational-health-check
```

Run local-only daily smoke:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --season-code 2526 --leagues E0,E1,SP1,D1,I1,F1 --slate-type historical --max-matches 10 --skip-download --run-quick-audit
```

Run with downloads enabled:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --season-code 2526 --fallback-season-code 2425 --leagues E0,E1,SP1,D1,I1,F1 --slate-type historical --max-matches 10 --run-quick-audit
```

Output goes to `outputs/runs/YYYY-MM-DD/`, which is ignored. Commit source, docs, tests, and small examples only.
