# Free Current Data Roadmap

Phase 21 starts the post-v1 data-source roadmap.

We are not using current paid StatsBomb. StatsBomb Open Data remains valuable, but it is historical validation/event-style data only for this project.

## Why Free Source Adapters

Before free current data feeds projections, the project needs to know:

- which source has which fields
- whether the source is current
- whether it covers clubs, internationals, or World Cup
- whether it has xG, lineups, ratings, event actions, odds, or style proxies
- what fields are missing
- whether the source is reliable enough for projection inputs

## Source Priority

Club projection:

- Football-Data
- ClubElo
- Understat
- FBref
- SofaScore

International and World Cup projection:

- EloRatings
- SofaScore
- FBref
- manual fallback
- StatsBomb Open Data for historical validation only

Style/event proxy work:

- WhoScored
- SofaScore
- FBref
- StatsBomb Open Data for historical validation only

## Source Notes

- Football-Data: current club results, fixtures, match stats, and odds fields when present. No event/tracking data.
- SoccerData: optional wrapper ecosystem. Useful only if installed and stable.
- SofaScore: candidate for current fixtures, scores, stats, xG/xGOT, lineups, player ratings, and World Cup coverage.
- WhoScored: candidate for event/action style proxies, but likely fragile.
- FBref: candidate for team/player aggregate stats.
- Understat: candidate for club xG and shot-level club data. Not a World Cup solution.
- ClubElo: candidate club strength prior.
- EloRatings: candidate national-team and World Cup strength prior.
- StatsBomb Open Data: historical event validation only.

## Reliability Rules

- No paid APIs.
- No current StatsBomb.
- No login, paywall, anti-bot, or CAPTCHA bypass.
- No fragile scraping in tests.
- Network probing must be optional and polite.
- Cache raw/source outputs when live probes are implemented.

## Connection To Future Style Work

Free current sources can improve style context only after coverage and reliability are measured. Free proxy data should never be described as true tracking data.

