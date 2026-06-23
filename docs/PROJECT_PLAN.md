# Project Plan

## Phase 4 Goal

Phase 4 builds the real-data projection foundation for the soccer style engine. The edge remains style-first: projections must be traceable to measured behavior before any score model is allowed to adjust expected goals.

## Architecture

- `src/data_ingestion/` loads local StatsBomb Open Data JSON and football-data.co.uk style CSVs.
- `src/features/` converts events into one team-match row, then builds rolling team style profiles.
- `src/agents/` creates deterministic identity and matchup explanations from measured metrics.
- `src/models/` estimates baseline xG, applies capped style adjustments, creates Poisson score probabilities, and backtests without future leakage.
- `src/reports/` writes CSV/Markdown outputs.
- `src/cli.py` exposes build, identity, matchup, projection, and backtest commands.

## Data Flow

1. Load local raw files.
2. Build `data/processed/team_match_style_log.csv`.
3. Build rolling `data/processed/team_style_profiles.csv`.
4. Classify style identity and matchup edges from profile metrics.
5. Estimate baseline expected goals from prior goals/xG.
6. Apply capped, traceable style adjustments.
7. Generate score probabilities and reports.
8. Backtest baseline-only versus style-adjusted projections.

## Phase Boundaries

This phase does not produce betting recommendations, staking guidance, or a frontend. Human scouting notes may be added later but must remain separate from measured evidence.
