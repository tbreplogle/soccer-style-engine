# Baseline Tuning

Baseline tuning is diagnostic-only. It explores transparent rating-baseline parameters and writes candidate evidence, but it does not change production defaults.

## What It Tests

The tuning grid can vary:

- rating-difference-to-goal scale
- baseline total goals
- neutral-site home adjustment
- draw dampening
- total goals adjustment

Every candidate is evaluated against completed rows with measurable results. Candidates are labeled conservatively, including `keep_current_baseline`, `candidate_improves_wdl`, `candidate_improves_totals`, `candidate_balanced_improvement`, `candidate_overfits_or_unstable`, `needs_holdout_validation`, and related total-goals warnings.

## Commands

Run calibration without tuning:

```bash
python -m src.cli calibrate-baseline-projections --data-source international_historical --min-rows 50
```

Run a small diagnostic grid:

```bash
python -m src.cli calibrate-baseline-projections --data-source international_historical --min-rows 50 --run-tuning --tuning-profile small --primary-metric composite
```

Save a candidate config for preview:

```bash
python -m src.cli calibrate-baseline-projections --data-source international_historical --min-rows 50 --run-tuning --save-tuning-candidates
```

Run with holdout dates:

```bash
python -m src.cli calibrate-baseline-projections --data-source international_historical --run-tuning --train-end-date 2021-12-31 --holdout-start-date 2022-01-01 --holdout-end-date 2022-12-31
```

Preview a candidate on current international projections:

```bash
python -m src.cli project-current-international --as-of-date 2026-06-25 --candidate-config outputs/calibration/YYYY-MM-DD/international_historical/RUN_ID/baseline_tuning/candidate_model_config.json
```

## Outputs

Each calibration run writes to:

```text
outputs/calibration/YYYY-MM-DD/<data_source>/<run_id>/
```

Tuning outputs live inside the run folder:

- `baseline_tuning/baseline_tuning_summary.md`
- `baseline_tuning/baseline_tuning_grid.csv`
- `baseline_tuning/baseline_tuning_best_candidates.csv`
- `baseline_tuning/baseline_tuning_manifest.json`
- `baseline_tuning/candidate_model_config.json` when requested
- `baseline_tuning/train_metrics.csv` and `holdout_metrics.csv` when holdout validation is requested

Candidate preview outputs are written under the current international run:

- `candidate_preview/candidate_projection_comparison.csv`
- `candidate_preview/candidate_projection_comparison_summary.md`

## Guardrails

Candidate configs are preview artifacts only. They do not replace production defaults, do not add style-aware adjustments, do not use current StatsBomb live data, and do not produce betting recommendations.

Use holdout validation before treating any candidate as more than a diagnostic signal.
