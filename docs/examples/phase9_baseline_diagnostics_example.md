# Phase 9 Baseline Diagnostics Example

This is an example report format. It does not include raw Football-Data CSV content.

## Example Result

| baseline_mode | total_goals_mae | note |
| --- | --- | --- |
| goals | 1.31 | transparent fallback |
| shots | 1.28 | useful when shots/SOT exist |
| market | 1.30 | odds anchor helps relative strength |
| totals_market | 1.29 | useful when O/U prices exist |
| blended | 1.27 | best example baseline |

## Interpretation

If the blended baseline is best or close to best across windows, use it as the default. Proxy score adjustments remain disabled unless future diagnostics show consistent lift.
