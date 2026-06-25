# Phase 25 Poisson Output Example

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --run-current-international --manual-matchups data/sample/current_international_matchups.csv --no-network --build-poisson-board
```

Writes:

- `outputs/projection_checkpoints/2026-06-24/poisson/poisson_1x2.csv`
- `outputs/projection_checkpoints/2026-06-24/poisson/poisson_totals.csv`
- `outputs/projection_checkpoints/2026-06-24/poisson/poisson_btts.csv`
- `outputs/projection_checkpoints/2026-06-24/poisson/poisson_clean_sheets.csv`
- `outputs/projection_checkpoints/2026-06-24/poisson/poisson_correct_score_matrix.csv`
- `outputs/projection_checkpoints/2026-06-24/poisson/poisson_match_summary.csv`
- `outputs/projection_checkpoints/2026-06-24/poisson/poisson_summary.md`

Poisson uses projected home xG and away xG as lambda values. It does not create style-aware inputs by itself.

Generated CSVs include fair decimal odds and model-implied American odds. Correct-score labels use Excel-safe spacing, for example `1 - 0`.
