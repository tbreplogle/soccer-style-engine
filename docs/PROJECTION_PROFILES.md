# Projection Profiles

Phase 10 adds projection profiles so a current-match projection can state what it is optimized to explain.

## Profiles

`score_projection` is the balanced default. It uses the blended baseline and reports xG, exact score distribution, W/D/L probabilities, and totals.

`winner_probability` prioritizes W/D/L calibration. When 1X2 odds are available it prefers the market baseline; otherwise it falls back to blended model evidence.

`total_goals` prioritizes projected total and over/under probabilities. When totals odds are available it prefers the totals-market baseline; otherwise it falls back to goals-only evidence.

`market_anchored` gives market information a stronger anchor while still producing model-derived xG. It does not copy the market probability table.

`model_only` removes market odds from the baseline blend. It is useful for comparing the model against market context.

## Guardrails

Proxy score adjustments remain disabled by default. Free proxy style fields are context from basic match statistics and odds; they are not true event, tracking, or 360 data.

Market gaps are diagnostic context. They show where the model and market differ, but they are not betting picks or staking instructions.

