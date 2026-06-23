# Phase 7 Real Football-Data Smoke Test

This report is a small committed summary of a real Football-Data.co.uk smoke test. It does not include the raw downloaded CSV, generated processed data, betting picks, or true event/tracking claims.

## Data Source

- URL used: `https://www.football-data.co.uk/mmz4281/2526/E0.csv`
- Local ignored path: `data/raw/football-data/E0_2526.csv`
- League/season: EPL, 2025-2026
- Normalized rows: 380
- Date range: 2025-08-15 to 2026-05-24
- Teams found: 20
- Missing goals rows: 0
- Missing shots rows: 0
- Missing shots-on-target rows: 0
- Missing corners rows: 0
- Rows with 1X2 odds available: 380

## Proxy Snapshot

Top control_proxy teams:

1. Man City
2. Arsenal
3. Tottenham
4. Liverpool
5. Brighton

Top attacking_pressure_proxy teams:

1. Man City
2. Man United
3. Liverpool
4. Brighton
5. Arsenal

Top defensive_shell_proxy teams:

1. Arsenal
2. Tottenham
3. Man City
4. Bournemouth
5. Brighton

Top tempo_proxy teams:

1. Liverpool
2. Man United
3. Nott'm Forest
4. Man City
5. Brentford

No teams were low reliability in this full-season smoke test.

## Projection Smoke Test

- As-of date: 2026-05-25
- Matchup: Arsenal vs Chelsea
- Data mode: `free_proxy_style`
- Home base xG: 1.829
- Away base xG: 0.6515
- Home proxy adjustment: +0.05
- Away proxy adjustment: -0.05
- Home final xG: 1.879
- Away final xG: 0.6015
- Most likely score: 1-0
- Projected total: 2.4805
- Home win probability: 0.6803
- Draw probability: 0.2086
- Away win probability: 0.1110

The projection warning explicitly states: `free_proxy_style is not true event/tracking style`.

## Backtest Smoke Test

- Date range: 2026-05-01 to 2026-05-24
- Matches: 41
- Home goals MAE: 1.044
- Away goals MAE: 0.722
- Total goals MAE: 1.106
- W/D/L log loss: 1.094
- Brier score: 0.221
- Exact score hit rate: 0.122
- Over/under 2.5 accuracy: 0.537
- Proxy lift vs baseline total MAE: -0.011

In this smoke window, the proxy layer slightly hurt total-goals MAE versus the baseline. Treat this as a diagnostic result, not a final model judgment.

## Limitations

- Football-Data match stats do not provide true possession, pass networks, player movement, defensive line height, compactness, or tracking.
- Phase 7 uses `free_proxy_style`; these are shots/corners/SOT/cards/odds proxies only.
- The downloaded raw CSV is intentionally ignored by git.
- Generated normalized data, projections, and backtest outputs are intentionally ignored by git.
- No betting recommendations are produced.

## Next Recommendation

Run smoke tests across multiple leagues/seasons, then compare where proxy adjustments help or hurt relative to the baseline. If proxy lift remains neutral or negative, tighten or reduce proxy adjustments before using them in any score projection workflow.
