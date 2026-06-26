# Current Result Grading

Phase 35 adds a post-match grading loop for saved current projections.

The grading command compares a saved projection CSV to completed results from an allowed cache or an explicit manual result CSV. If no completed results are available, the command writes a clean no-results status. It does not create scores.

## Command

```powershell
.\.venv\Scripts\python.exe -m src.cli grade-current-projections --as-of-date 2026-06-25 --actual-results data/manual/results_2026_06_25.csv
```

Manual result CSV schema:

- `fixture_date`
- `home_team`
- `away_team`
- `home_goals`
- `away_goals`
- `source_name`
- `notes` optional

Manual rows are labeled `manual_source_supplied`.

## Outputs

```text
outputs/grading/YYYY-MM-DD/<run_id>/
```

Files:

- `current_projection_grading_summary.md`
- `graded_matches.csv`
- `scoreline_miss_types.csv`
- `result_grading_manifest.json`

## What Gets Graded

The grading loop records actual score, exact-score hit, top 3/top 5 hit, actual score rank, W/D/L correctness, O/U 2.5 Brier component, BTTS Brier component, and miss type.

Miss types include winner wrong, draw missed, total too low/high, favorite or underdog attack underestimated, both teams scored missed, clean sheet missed, close scoreline, exact score hit, and insufficient data.

