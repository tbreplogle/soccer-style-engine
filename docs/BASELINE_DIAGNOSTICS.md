# Baseline Diagnostics

Phase 9 exists because free proxy score adjustments have not earned default xG impact. Current free projections should be carried by transparent baselines first.

## Baseline Modes

- `goals`: team goals for/against, league average goals, and home advantage.
- `shots`: shots and shots on target converted through league conversion rates, with a goals fallback.
- `market`: 1X2 odds anchor relative team strength without blindly copying market prices.
- `totals_market`: over/under 2.5 odds adjust total-goals pressure when available.
- `blended`: explicit conservative blend of goals, shots, market, and totals components.

## Market Guardrail

Odds are de-vigged and used as an anchor/helper. They do not fully dictate xG, and missing odds fall back to non-market baselines.

## Interpreting Diagnostics

Compare total-goals MAE, W/D/L log loss, Brier score, calibration, and mean projected total versus actual total. Prefer `blended` only when it performs at least competitively across windows. Proxy score adjustments remain disabled by default.
