# Operational Runner

The daily runner creates a repeatable operational run under:

```text
outputs/runs/YYYY-MM-DD/
```

Each run can download Football-Data CSVs, normalize available local data, build a club slate report, compare key profile outputs for one matchup, optionally run a quick leakage audit, optionally build an international slate, and write a manifest plus a concise run summary.

Typical command:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --season-code 2526 --leagues E0,E1,SP1,D1,I1,F1 --slate-type historical --max-matches 10 --run-quick-audit
```

Local files only:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --skip-download --slate-type historical
```

Manual club matchups:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2026-05-25 --skip-download --slate-type manual --manual-club-matchups data/sample/manual_club_matchups.csv
```

Optional international slate:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date 2022-12-01 --skip-download --include-international --international-input data/processed/international_match_results.csv --manual-international-matchups data/sample/manual_international_matchups.csv
```

International is optional. If requested data is missing, the runner warns and still completes the club run.

Generated run files remain ignored and should not be committed.
