# Phase 14 Leakage Audit Example

Synthetic clean result:

- Leakage checks passed: true
- Failed checks: none
- Recommendation: pass

Synthetic failed result:

- A `future_leakage_flag` column set to true is detected.
- Recommendation: fix failed leakage checks before validation.

The audit checks process integrity; it does not score model quality.
