# Confidence Scoring

Projection confidence is an interpretation layer, not a claim of certainty.

The score runs from 0 to 100 and maps to:

- `High`: strong available evidence and no major disagreement flags.
- `Medium`: usable evidence with some missing data, moderate disagreement, or normal uncertainty.
- `Low`: insufficient prior matches, missing core data, or major disagreement.

## Inputs

The confidence module considers:

- prior match sample size for both teams
- goals data availability
- shots, shots on target, and corner availability
- 1X2 odds availability
- totals odds availability
- disagreement across baseline modes
- model-market probability gaps
- whether proxy score adjustments are enabled
- data quality flags and recent-match sample size

Fewer than 6 prior matches for either team usually produces Low confidence. Missing goals data is treated as a severe risk. Missing shots or odds reduces confidence but does not invalidate a projection.

## Interpretation

High confidence means the projection has stronger support from available data. It does not mean the result is likely to be correct in a single match.

Low confidence means the projection should be read as rough context. Proxy-only evidence does not increase confidence because free proxy style is not event or tracking style.

Market disagreement is flagged, not treated as a betting signal.

