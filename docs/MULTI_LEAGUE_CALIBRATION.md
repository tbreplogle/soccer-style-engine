# Multi-League Calibration

Phase 11 tests projection profiles and confidence labels beyond a single EPL window.

One league window is not enough because scoring rates, odds coverage, shot data quality, home advantage, and fixture density can vary by league. A profile that looks strong in one league can become average elsewhere.

## Rules

- Each league is calibrated separately.
- Teams are compared only inside their league unless a future cross-league module explicitly says otherwise.
- Raw Football-Data CSVs stay in ignored local storage under `data/raw/football-data/`.
- Processed multi-league outputs stay ignored under `data/processed/`.
- Proxy score adjustments remain disabled by default.

## Outputs

`diagnose-multi-league-profiles` writes:

- `outputs/reports/multi_league_profile_diagnostics_summary.md`
- `outputs/reports/multi_league_profile_diagnostics_results.csv`
- `outputs/reports/confidence_calibration_summary.md`

These are generated reports and should not be committed.

