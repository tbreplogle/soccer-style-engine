# Leakage Audit

The leakage audit checks that validation and projection workflows do not accidentally use future information.

Run:

```powershell
.\.venv\Scripts\python.exe -m src.cli audit-leakage --input data/processed/multi_season_match_results.csv --start-date 2021-08-01 --end-date 2026-05-31
```

The audit checks prior-only dates, league-season grouping, explicit market-aware odds usage, target final-score leakage fields, and generated validation slate safety. It is designed to run on both synthetic fixtures and normalized real Football-Data rows.

Passing this audit does not prove the model is good. It only lowers the risk that validation metrics were inflated by future match outcomes or mixed grouping.
