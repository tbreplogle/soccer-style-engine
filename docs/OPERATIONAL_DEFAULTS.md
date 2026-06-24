# Operational Defaults

Phase 15 centralizes the defaults used by day-to-day club slate runs.

Club defaults:

- General report profile: `score_projection`
- Primary W/D/L context profile: `winner_probability`
- Default baseline mode: `blended`
- Proxy adjustments enabled: `false`
- Confidence language: `data_support_context`
- Default leagues: `E0,E1,SP1,D1,I1,F1`
- Current season code: `2526`
- Fallback season code: `2425`

These defaults follow Phase 14: `winner_probability` was strongest for W/D/L across the validation set, while `score_projection` remains the clearest general projection report view. Totals remain less settled and should be treated as a later calibration target.

Confidence remains context-only. Reports should prefer Data Support or Risk Context wording over claims that High/Medium/Low labels are calibrated certainty.

Proxy score adjustments remain disabled by default. Current free proxy style is not true tracking or event style.

No betting recommendations, picks, or play/take language are allowed.
