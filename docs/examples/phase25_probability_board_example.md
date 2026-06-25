# Phase 25 Probability Board Example

The intended product path is:

```text
style-aware projected xG -> Poisson probability board
```

Current Phase 25 probability board fields include:

- projected home xG
- projected away xG
- projected total
- 1X2 probabilities
- over/under probabilities
- BTTS probabilities
- clean sheet probabilities
- correct score matrix
- fair decimal odds
- model-implied American odds
- data support labels
- warnings for rating-only, manual, or sample/demo support

Current rows are baseline/rating-only unless `style_inputs_available=true` is backed by measurable inputs.

Correct-score labels are written as `1 - 0` instead of `1-0` to avoid spreadsheet date parsing.
