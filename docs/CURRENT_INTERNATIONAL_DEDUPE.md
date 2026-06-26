# Current International Fixture Deduplication

Current international fixture sources can overlap. For example, OpenFootball and ESPN may both publish the same match with different kickoff string formats.

Phase 32 deduplication uses fixture identity first:

- fixture date
- normalized competition
- normalized home team
- normalized away team
- resolved/unresolved status

Kickoff time is normalized and audited, but it does not prevent deduplication when date, teams, competition, and resolved status match.

## Kickoff Normalization

Common kickoff formats are retained as raw text and normalized into audit fields:

- `kickoff_time_raw`
- `kickoff_time_normalized`
- `kickoff_datetime_normalized`
- `kickoff_timezone_status`
- `kickoff_parse_warning`

Explicit UTC offsets are preserved and converted to UTC for comparison. Time strings without a timezone are not assigned an invented timezone.

## Dedupe Fields

Projection and slate outputs include:

- `fixture_key`
- `dedupe_match_key`
- `deduplication_status`
- `primary_source`
- `duplicate_sources`
- `dedupe_time_comparison`
- `dedupe_time_delta_minutes`
- `source_priority_score`

Swapped neutral-site candidates are flagged as `possible_duplicate_review` and are not silently merged.

## Reports

Reports are written under `outputs/current_international/YYYY-MM-DD/fixture_deduplication/`:

- `fixture_deduplication_summary.md`
- `deduplicated_fixtures.csv`
- `duplicate_fixtures.csv`
- `possible_duplicate_review.csv`
- `source_priority_summary.csv`
- `dedupe_consistency_check.csv`
- `projection_checkpoint_consistency.md`

The projection checkpoint consistency report compares direct current projections against checkpoint rows for the same slate settings.
