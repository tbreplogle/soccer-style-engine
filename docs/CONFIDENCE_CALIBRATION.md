# Confidence Calibration

Confidence labels are useful only if they hold up in backtests.

Phase 11 audits whether High confidence projections actually outperform Medium or Low confidence projections across leagues. It checks W/D/L log loss and total-goals MAE by confidence bucket.

## Recommendations

The audit returns one of:

- `strong_confidence_labels_ok`
- `use_soft_confidence_language`
- `confidence_context_only`
- `needs_more_data`

If High confidence does not consistently perform better, the engine should use softer language. That means confidence should be described as evidence quality and risk context, not certainty.

## Current Interpretation

High confidence means stronger data support. It does not mean a single match is predictable. Medium and Low should be read as progressively more uncertainty, missing data, or disagreement across baselines and market context.

