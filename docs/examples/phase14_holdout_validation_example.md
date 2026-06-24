# Phase 14 Holdout Validation Example

Synthetic split:

- Train: 2122, 2223, 2324
- Validation: 2425
- Test: 2526

The selected default is chosen from train and validation only. Test-season metrics are reported after selection and must not be used to tune the selection rule.

Example recommendation values include `prefer_score_projection`, `prefer_winner_probability_for_wdl`, or `soften_confidence_language`.
