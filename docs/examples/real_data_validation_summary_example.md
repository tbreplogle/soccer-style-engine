# Real Data Validation Summary Example

This is example output from the Phase 5 validator using synthetic StatsBomb-style sample files. It is not a real team projection.

## Validation Set

Matches loaded: 1

Team-match rows created: 2

## Data Quality Flags

| data_quality_flag | rows |
| --- | --- |
| event_only | 2 |

## Warnings

- 360/tracking-aware fields are missing or nullable in the sample.
- Event-only proxy metrics should not be described as tracking facts.
- Synthetic sample data exists only to test the validation pipeline.

## Recommended Next Validation Step

Download StatsBomb Open Data locally under `data/raw/statsbomb-open-data/` and run the validator on 10 real matches from one competition/season.
