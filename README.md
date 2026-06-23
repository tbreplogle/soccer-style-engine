# Soccer Style Engine - Phase 4 Real Data + Projection Foundation

This project tracks how teams play before making score projections.

The rule of this project remains:

> We do not predict first. We track how teams play first, then use that tracked identity to explain matchups.

## What Phase 4 Adds

1. Local StatsBomb Open Data JSON ingestion.
2. Local football-data.co.uk CSV normalization.
3. Event-based team-match style metrics.
4. Rolling team style profiles using only prior matches.
5. Deterministic identity and matchup intelligence.
6. Conservative baseline xG plus capped style adjustments.
7. Independent Poisson score probabilities.
8. Rolling backtest scaffolding with leakage guardrails.

## What This Is Not

This is not a betting app, a frontend, or a black-box ML system. It does not make unsupported claims from team reputation.

## Key Commands

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m src.cli build-style-log --statsbomb-root data/raw/statsbomb-open-data --competition-id 1 --season-id 1
.\.venv\Scripts\python.exe -m src.cli build-profiles --as-of-date YYYY-MM-DD
.\.venv\Scripts\python.exe -m src.cli identity --team "Team Name" --as-of-date YYYY-MM-DD
.\.venv\Scripts\python.exe -m src.cli matchup --home "Team A" --away "Team B" --as-of-date YYYY-MM-DD
.\.venv\Scripts\python.exe -m src.cli project --home "Team A" --away "Team B" --as-of-date YYYY-MM-DD
.\.venv\Scripts\python.exe -m src.cli backtest --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

## Output Files

- `data/processed/team_match_style_log.csv`
- `data/processed/team_style_profiles.csv`
- `data/processed/match_results.csv`
- `outputs/projections/match_projection.csv`
- `outputs/reports/backtest_results.csv`
- `outputs/reports/backtest_summary.md`

## Important Guardrail

If data is missing, the engine outputs nulls or low-confidence flags. Synthetic files under `data/sample/` are test fixtures only.
