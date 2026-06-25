# Current International Data

Phase 22 adds a current international data layer for World Cup-style workflows. Phase 23 adds the first real current-source probe for SofaScore. Phase 24 adds the stable OpenFootball + EloRatings fixture/rating backbone.

The layer separates four things:

- Fixture sources: OpenFootball/static fixture JSON first, SofaScore cache only if already available, ESPN scoreboard fallback, or manual fallback.
- Strength priors: EloRatings-style national-team ratings when a local cache is available.
- Match stats/xG: SofaScore can now be probed and cached; no current xG is inferred from fixture-only data.
- Projection outputs: existing international projections wrapped with current-source support labels.

## Guardrails

- Current StatsBomb is not used.
- Fixture-only sources are not true event, tracking, xG, lineup, or style data.
- Manual fallback rows are explicit inputs and must not be mistaken for automated current feeds.
- No Selenium, login, CAPTCHA, anti-bot, or paywall bypass is used.
- No betting recommendations are produced.
- Proxy score adjustments remain disabled.
- TheStatsAPI/API-key/signup sources are not part of the Phase 24 no-signup workflow.

## Commands

```bash
python -m src.cli audit-current-international --as-of-date 2026-06-24 --no-network
python -m src.cli build-worldcup-backbone --as-of-date 2026-06-24 --no-network
python -m src.cli probe-sofascore --as-of-date 2026-06-24 --no-network
python -m src.cli build-current-international-slate --manual-matchups data/sample/current_international_matchups.csv --as-of-date 2026-06-24 --no-network
python -m src.cli project-current-international --manual-matchups data/sample/current_international_matchups.csv --as-of-date 2026-06-24 --no-network --max-matches 10
```

Generated outputs are written below `outputs/current_international/` and are ignored by git.

Phase 27 adds the source harvest/audit layer documented in `docs/CURRENT_INTERNATIONAL_SOURCE_HARVEST.md`. Use `audit-current-international-sources` to inspect fixture, rating, stat, and match coverage before running strict current projections.
SofaScore probe outputs are written below `outputs/source_probes/sofascore/` and are also ignored.

