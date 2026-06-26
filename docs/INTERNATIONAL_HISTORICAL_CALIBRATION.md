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
Calibration outputs are written under `outputs/calibration/YYYY-MM-DD/`.

Generated outputs are ignored by git. Commit source, tests, docs, and placeholders only.

## Style Readiness

The calibrated baseline is the benchmark future style layers must beat. The most valuable next style inputs are shots for/against, xG for/against, open-play and set-piece xG, possession or field-tilt proxies, transition/directness proxies, discipline, and verified absence or injury inputs.

No current StatsBomb live data is used.
No betting recommendations are produced.
Proxy adjustments remain disabled by default.
