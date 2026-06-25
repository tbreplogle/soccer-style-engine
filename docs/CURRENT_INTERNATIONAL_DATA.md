# Current International Data

Phase 22 adds a current international data layer for World Cup-style workflows.

The layer separates four things:

- Fixture sources: OpenFootball, TheStatsAPI, SofaScore, ESPN scoreboard, or manual fallback.
- Strength priors: EloRatings-style national-team ratings when a local cache is available.
- Match stats/xG: planned adapter space only; no current xG is inferred from fixture-only data.
- Projection outputs: existing international projections wrapped with current-source support labels.

## Guardrails

- Current StatsBomb is not used.
- Fixture-only sources are not true event, tracking, xG, lineup, or style data.
- Manual fallback rows are explicit inputs and must not be mistaken for automated current feeds.
- No Selenium, login, CAPTCHA, anti-bot, or paywall bypass is used.
- No betting recommendations are produced.
- Proxy score adjustments remain disabled.

## Commands

```bash
python -m src.cli audit-current-international --as-of-date 2026-06-24 --no-network
python -m src.cli build-current-international-slate --manual-matchups data/sample/current_international_matchups.csv --as-of-date 2026-06-24 --no-network
python -m src.cli project-current-international --manual-matchups data/sample/current_international_matchups.csv --as-of-date 2026-06-24 --no-network --max-matches 10
```

Generated outputs are written below `outputs/current_international/` and are ignored by git.

