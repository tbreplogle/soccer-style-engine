# World Cup Fixture + Elo Backbone

Phase 24 makes the current World Cup/international workflow useful without pretending it is complete style analysis.

## Source Policy

The Phase 24 default backbone uses:

- OpenFootball/football.db-style static fixture JSON
- EloRatings-style national-team ratings from local cache or committed sample
- manual fallback CSV
- ESPN scoreboard only as optional fallback

It does not use TheStatsAPI, API-Football, Sportmonks, API-key sources, signup-required sources, paid APIs, or current StatsBomb.

SofaScore is not required for Phase 24. Phase 23 showed safe basic SofaScore requests returned HTTP 403, and this project does not bypass blocks.

## Rating-Only Projection Role

Rating-only projections are a baseline score projection, not the final model. They estimate a conservative expected-goals split from national-team strength ratings and fixture context.

Every rating-only report should communicate:

> This is a baseline score projection based on fixture + rating support only. It does not include current event data, xG, lineups, injuries, or style-aware matchup inputs yet.

## Support Labels

- `medium_current_fixture_rating`: static/current fixture plus both team ratings.
- `low_fixture_only`: fixture exists without complete rating support.
- `low_manual_fixture_rating`: manual fallback fixture, with or without sample ratings.
- `insufficient`: no usable fixture.

## What Is Still Missing

The backbone does not include current event data, xG, lineups, injuries, player availability, tactical style, transition risk, field tilt, or matchup-style adjustments. Those are future projection inputs, not claims made by Phase 24.

