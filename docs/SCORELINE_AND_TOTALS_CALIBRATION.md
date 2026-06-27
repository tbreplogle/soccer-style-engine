# Scoreline And Totals Calibration

Phase 35 adds diagnostic scoreline and totals calibration before any future style-aware xG layer.

Poisson score matrices often put the single highest-probability cell around `1-0`, `1-1`, or `0-1` when the projected total sits near 2.3 to 2.4 goals. That can be mathematically reasonable because exact scores are naturally low-probability outcomes. The issue to monitor is not one low score cell; it is whether the full distribution is too compressed and fails to cover actual scores in the top 3 or top 5 cells.

## Outputs

Scoreline diagnostics write under:

```text
outputs/calibration/YYYY-MM-DD/scoreline_diagnostics/<run_id>/
```

Files:

- `scoreline_diagnostics_summary.md`
- `scoreline_metrics.csv`
- `scoreline_topk_metrics.csv`
- `team_goal_band_calibration.csv`
- `total_goal_band_calibration.csv`
- `actual_score_rankings.csv`

## Metrics

The diagnostic module measures exact-score coverage, top 3/top 5 coverage, actual score rank, average actual score probability, home/away/total goal MAE, O/U 2.5 Brier, BTTS Brier, team goal bands, and total goal bands.

Diagnostic labels include totals too low/high, scorelines too compressed, favorites too capped, underdogs too high, draw cluster too high, needs more goal spread, and insufficient rows.

## Phase 36 xG Compression Audit

Phase 36 audits formulas for hidden xG compression. Earlier current rating projection logic used a hard rating-difference clamp, a narrow total-goals clamp, a home-share clamp, and a `0.35` team xG floor. Those bounds can cluster most likely exact scores around `1-0`, `1-1`, and `0-1`.

The current rating baseline now avoids artificial favorite xG caps and underdog floors in normal production calculation. It keeps only broad reported safety guards:

- team xG cannot be negative
- missing/non-numeric xG falls back to a neutral value with a warning
- team xG above `5.00` is lowered by an explicit sanity guard

When a guard is applied, projection output includes `xg_safety_guard_applied` and `xg_safety_guard_reason`.

## Guardrails

This report is diagnostic only. It does not change production defaults, create results, use current StatsBomb live data, or enable proxy/style adjustments.

