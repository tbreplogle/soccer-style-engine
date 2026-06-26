# International Historical Calibration

The current international projection model is a rating-based baseline. It can produce projected xG, W/D/L probabilities, likely scores, and a Poisson board from fixture plus team rating support, but it is not style-aware and must not be called calibrated until leakage-safe historical validation supports that claim.

## Historical Inputs

Leakage-safe international calibration requires:

- completed historical international results
- dated rating snapshots for both teams
- snapshot dates on or before the match date
- snapshot age within the configured threshold

Current ratings must not be used to backtest old matches unless the run is explicitly labeled `diagnostic_only_current_rating_leakage`.

## Commands

Seed historical calibration inputs:

```bash
python -m src.cli seed-international-historical-calibration-data --start-date 2018-01-01 --end-date 2026-06-25 --all --allow-network
```

Run international calibration:

```bash
python -m src.cli calibrate-baseline-projections --data-source international_historical --min-rows 50
```

If historical snapshots or results are missing, the command writes a blocked calibration report instead of falling back to current ratings.

## Outputs

Historical seed outputs are written under `outputs/calibration/YYYY-MM-DD/historical_seed/`.
Calibration outputs are written under immutable run folders:

```text
outputs/calibration/YYYY-MM-DD/<data_source>/<run_id>/
```

Each run folder preserves:

- `baseline_calibration_summary.md`
- `wdl_calibration.csv`
- `totals_calibration.csv`
- `probability_buckets.csv`
- `scoreline_calibration.csv`
- `calibration_manifest.json`

The manifest includes `calibration_run_id`, `calibration_data_source`, `calibration_output_dir`, `calibration_created_at`, and `calibration_config_hash`.

The date folder also writes:

- `latest_manifest.json`
- `<data_source>/latest_manifest.json`
- `calibration_run_index.csv`

These files let review tools find the latest run without overwriting older calibration evidence.

Generated outputs are ignored by git. Commit source, tests, docs, and placeholders only.

## Diagnostic Tuning

Optional baseline tuning is documented in `docs/BASELINE_TUNING.md`. It is diagnostic-only and writes candidate configs only when requested. It does not alter production defaults or claim style-aware improvement.

## Style Readiness

The calibrated baseline is the benchmark future style layers must beat. The most valuable next style inputs are shots for/against, xG for/against, open-play and set-piece xG, possession or field-tilt proxies, transition/directness proxies, discipline, and verified absence or injury inputs.

No current StatsBomb live data is used.
No betting recommendations are produced.
Proxy adjustments remain disabled by default.
