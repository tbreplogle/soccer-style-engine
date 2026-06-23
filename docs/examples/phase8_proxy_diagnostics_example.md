# Phase 8 Proxy Diagnostics Example

This is example output format, not a real production result.

## Scenario

- Input: synthetic Football-Data-style sample
- Date range: 2026-01-15 to 2026-02-15
- Tested caps: `0`, `0.03`, `0.05`
- Data mode: `free_proxy_style`

## Example Recommendation

`use_proxy_adjustments_context_only`

## Example Interpretation

Some proxy configurations helped in one window, but the signal was unstable. The conservative response is to keep proxy explanations available while leaving score adjustments disabled or capped very low until more real windows prove consistent lift.

## Guardrail

Proxy metrics are not true possession, movement, directness, pressing, compactness, or tracking. They are match-stat proxies from shots, corners, SOT, goals, cards, fouls, and odds.
