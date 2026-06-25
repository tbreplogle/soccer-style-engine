# Projection Results Checkpoint

Phase 25 adds a terminal-first review step for generated projection CSVs. It checks whether score projections, totals, W/D/L probabilities, confidence labels, data support, and style-input claims are sane before a human treats the outputs as useful.

It also writes a Poisson probability board from projected team xG. The intended product shape is:

```text
fixture -> baseline strength -> future style-aware adjustment -> projected team xG -> Poisson probability board
```

The checkpoint is a review tool. It does not add data sources, make betting picks, enable proxies by default, or claim rating-only rows are true style-aware projections.

## Command

Review an existing projection CSV:

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --projection-file outputs/current_international/2026-06-24/current_international_projections.csv
```

Run the current international no-network projection first, then review it:

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --run-current-international --no-network --max-matches 10
```

This command will not silently treat committed sample fixtures as real current games. If no real cache or manual matchup file exists, it returns a warning and zero projection rows.

Run a demo with committed sample fixtures:

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --run-current-international --no-network --allow-sample-data --build-poisson-board
```

Sample rows are labeled `is_sample_data=true`, `source_tier=sample`, `reliability_status=sample_only`, and `data_support_level=sample_demo_only`.

Include manual fallback matchups:

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --run-current-international --no-network --manual-matchups data/sample/current_international_matchups.csv --max-matches 10
```

Build the static viewer after the checkpoint:

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --run-current-international --no-network --build-viewer
```

## Outputs

Generated files are written under:

```text
outputs/projection_checkpoints/YYYY-MM-DD/
```

Each checkpoint writes:

- `projection_checkpoint_summary.md`
- `projection_checkpoint_rows.csv`
- `projection_checkpoint_flags.csv`
- `projection_checkpoint_manifest.json`
- `poisson/poisson_1x2.csv`
- `poisson/poisson_totals.csv`
- `poisson/poisson_btts.csv`
- `poisson/poisson_clean_sheets.csv`
- `poisson/poisson_correct_score_matrix.csv`
- `poisson/poisson_match_summary.csv`
- `poisson/poisson_summary.md`

These are generated outputs and should not be committed.

## Checks

The checkpoint flags warnings for:

- missing or extreme projected totals
- negative projected xG values
- missing W/D/L probabilities
- W/D/L probability sums not close to 1.0
- missing most likely score
- high confidence with rating-only or fixture-only support
- style-aware language when `style_inputs_available` is false
- rating-only rows missing a clear rating-only warning
- betting or action recommendation language

Warnings are review prompts, not automatic proof that a projection is bad.

## Poisson Board

Poisson uses projected home xG and away xG as lambda values and writes:

- 1X2 probabilities and fair decimal odds
- model-implied American odds
- over/under probabilities for 0.5 through 4.5
- BTTS yes/no probabilities
- clean sheet and concedes probabilities
- correct score matrix
- match summary with xG, most likely score, support labels, sample/manual flags, and warnings

These are probability outputs, not betting recommendations.

Score labels in generated CSVs use an Excel-safe format such as `1 - 0`, not `1-0`, so spreadsheet software does not turn scores into dates.

## Sample And Manual Rows

Files under `data/sample/` are demo/test fixtures only. They are not real current games by default.

Manual matchups are user supplied, not source-verified. They are labeled `source_tier=manual` and are not treated as sample data.

## Baseline to Beat

The current international baseline can produce rating/fixture-based score projections and probabilities. It cannot yet prove style-aware adjustment value. Future style adjustment work should beat this baseline on calibration or review usefulness without adding overclaims, high-confidence low-support rows, or action language.
