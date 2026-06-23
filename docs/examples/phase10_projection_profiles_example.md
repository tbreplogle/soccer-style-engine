# Phase 10 Projection Profiles Example

Example matchup: Arsenal vs Chelsea, as-of date `2026-05-25`.

This example is a compact report format for comparing projection profiles. It should not include raw downloaded CSV rows or generated report dumps.

## Profile Comparison

| projection_profile | expected behavior | market_influence_level | confidence use |
| --- | --- | --- | --- |
| `score_projection` | balanced score, total, and W/D/L view | Low if odds are present in blended baseline | default read |
| `winner_probability` | prioritizes W/D/L calibration | Medium when 1X2 odds exist | compare outcome probabilities |
| `total_goals` | prioritizes projected total and O/U context | Medium when totals odds exist | compare match total shape |
| `market_anchored` | stronger market anchor with model-derived xG | High when odds exist | inspect market-model disagreement |
| `model_only` | excludes market odds from baseline blend | None | compare model to market context |

## Confidence Explanation

Confidence is reduced by low prior-match sample size, missing goals or shot data, missing odds, large baseline disagreement, or large model-market gaps. Proxy-only support does not increase confidence.

## Market Gap Explanation

Market gap fields compare model W/D/L probabilities to de-vigged 1X2 probabilities where odds are available. A gap is a diagnostic disagreement flag, not a betting recommendation.

## Warnings

- `free_proxy_style` is not true event/tracking style.
- Proxy score adjustments remain disabled by default.
- High confidence does not mean a single match is predictable.
- This report is projection context, not a picks product.

## Next Recommendation

Run `diagnose-projection-profiles` on the current season window and compare whether High confidence buckets perform better than Medium or Low before changing defaults.

