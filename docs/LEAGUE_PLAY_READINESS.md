# League Play Readiness

League readiness checks whether club data is ready for current-season projection runs.

It does not create fixtures, results, ratings, xG, or style inputs. It only inventories local Football-Data processed files, calibration outputs, future fixture availability, and whether a small club slate can be generated from existing rows.

## Commands

Run club calibration:

```bash
python -m src.cli calibrate-baseline-projections --data-source club_historical --min-rows 500
```

Run diagnostic club tuning:

```bash
python -m src.cli calibrate-baseline-projections --data-source club_historical --min-rows 500 --run-tuning --tuning-profile small --primary-metric composite --save-tuning-candidates
```

Check league readiness:

```bash
python -m src.cli check-league-readiness --as-of-date 2026-06-25 --leagues E0,E1,SP1,D1,I1,F1 --require-calibration --build-viewer
```

Require future fixtures when league play is expected:

```bash
python -m src.cli check-league-readiness --as-of-date 2026-08-01 --require-calibration --require-current-fixtures
```

## Outputs

Readiness outputs are written under:

```text
outputs/club/YYYY-MM-DD/league_readiness/
```

Files:

- `league_readiness_summary.md`
- `league_readiness_by_league.csv`
- `club_data_inventory.csv`
- `club_projection_readiness.csv`
- `club_calibration_readiness.csv`
- `league_readiness_manifest.json`

Club calibration writes league and season breakdowns inside each club calibration run:

- `club_calibration_diagnostics.md`
- `club_calibration_filter_breakdown.csv`
- `league_calibration_summary.csv`
- `league_probability_buckets.csv`
- `league_totals_calibration.csv`
- `season_calibration_summary.csv`
- `league_season_calibration_summary.csv`

## Status Meanings

- `ready`: historical data, calibration, and current/future fixture requirements are satisfied.
- `ready_with_warnings`: enough data exists for review, but a non-required readiness item is missing, commonly future fixtures during offseason.
- `blocked_missing_current_fixtures`: future fixtures are required but absent.
- `blocked_missing_historical_data`: historical club rows are missing.
- `blocked_missing_calibration`: calibration is required but no club calibration fallback exists.
- `blocked_schema_error`: required columns are missing or unreadable.
- `blocked_insufficient_rows`: rows loaded, but too few rows survive eligibility filters.

## Club vs International Calibration

Club calibration uses historical Football-Data match results and a transparent goal-history baseline. It has a much larger row count and is the best near-term baseline tuning surface.

International calibration uses historical international results matched to dated rating snapshots. It remains separate because club and national-team contexts are not interchangeable.

Phase 34 compares latest club and international calibration in:

```text
outputs/calibration/YYYY-MM-DD/calibration_comparison_summary.md
```

That comparison is diagnostic only. It does not merge the models.

## Guardrails

Style-aware xG is still next, not part of this phase. Proxy/style adjustments remain disabled by default. Current StatsBomb live data is not used. No betting recommendations are produced.
