# Slate Outputs

Slate reports support three modes:

- `future_fixture_slate`: future rows with missing goals.
- `historical_validation_slate`: completed rows projected with match-date cutoffs to avoid future leakage.
- `manual_matchup_slate`: user-provided matchup CSVs or command-line teams.

Club slate outputs are written to:

- `outputs/reports/club_slate_report.md`
- `outputs/projections/club_slate_projections.csv`

International slate outputs are written to:

- `outputs/reports/international_slate_report.md`
- `outputs/projections/international_slate_projections.csv`

Profile comparisons are written to:

- `outputs/reports/projection_profile_comparison.md`
- `outputs/projections/projection_profile_comparison.csv`

These files are generated and ignored.

