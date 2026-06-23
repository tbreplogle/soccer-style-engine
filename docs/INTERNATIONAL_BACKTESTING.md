# International Backtesting

International backtests roll forward through selected matches and use only prior matches for each projection.

The backtest reports:

- Team A goals MAE
- Team B goals MAE
- total goals MAE
- W/D/L log loss
- Brier score
- exact score hit rate
- over/under 2.5 accuracy
- confidence bucket performance
- sparse-sample warning rate

The first matches in a tournament often have low confidence because prior national-team data is sparse or from old tournaments. That is expected and should be reported rather than hidden.

Generated files are ignored:

- `outputs/reports/international_backtest_summary.md`
- `outputs/reports/international_backtest_results.csv`

