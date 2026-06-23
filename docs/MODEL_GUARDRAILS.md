# Model Guardrails

## Evidence Rules

- No identity label may rely on team reputation.
- Every style label must include supporting metric evidence and conflicting evidence.
- Human scouting notes must be separated from measured evidence.
- Synthetic sample data must never be described as a real projection.

## Projection Rules

- Fewer than 5 prior matches for either team means low confidence.
- No event/location data means style adjustment is zero or heavily reduced.
- Missing 360/tracking means no off-ball or shape claim may be stated as fact.
- Recent lineup changes are not measured in this phase and must be listed as uncertainty.
- Individual style adjustments are capped at +/- 0.12 xG.
- Total style adjustment is capped at +/- 0.30 xG per team.
- Weak data quality halves the style adjustment.
- No betting recommendation output is allowed in this phase.

## Modeling Philosophy

The baseline uses transparent goals/xG strength and home advantage. The style layer is rule-based and conservative. Black-box machine learning is intentionally out of scope until larger real-data backtests justify it.
