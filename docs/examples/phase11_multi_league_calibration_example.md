# Phase 11 Multi-League Calibration Example

This is a committed example, not a generated report.

## Example Scope

Leagues:

- EPL
- Championship
- La Liga
- Bundesliga
- Serie A
- Ligue 1

Profiles:

- `score_projection`
- `winner_probability`
- `total_goals`
- `market_anchored`
- `model_only`

## Example Interpretation

If `winner_probability` leads W/D/L log loss in several leagues, it may be the best profile for outcome probabilities. If `market_anchored` or `total_goals` leads total-goals MAE, those profiles may be better for match total interpretation.

Confidence labels should only be treated as strong if High confidence buckets perform better than Medium or Low across more than one league. If not, use soft language such as "stronger evidence support" instead of implying certainty.

## Guardrails

- No raw Football-Data CSVs should be committed.
- Generated diagnostics stay under ignored report folders.
- Proxy xG adjustments remain disabled by default.
- Market gaps are context, not betting recommendations.

