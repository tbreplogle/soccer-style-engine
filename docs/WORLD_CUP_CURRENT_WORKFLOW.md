# World Cup Current Workflow

Use this workflow when current World Cup fixtures are needed but a verified current event feed is unavailable.

1. Audit available free sources with no network by default.
2. Build a current international slate from local cache or manual fallback fixtures.
3. Run projections through the existing international model.
4. Read the support labels before using any output.

## Support Labels

- `high_current_fixture_stats_xg`: current fixture stats include xG.
- `high_current_fixture_stats`: current fixture stats exist without xG.
- `medium_current_fixture_rating`: current fixture plus current strength rating.
- `medium_current_fixture_scoreboard_rating`: scoreboard fixture plus strength rating.
- `low_manual_fixture_rating`: manual fixture plus strength rating.
- `low_fixture_only`: fixture exists without current stats or ratings.
- `historical_context_only`: rating/historical context only.
- `insufficient`: no usable current fixture or rating.

The default manual sample demonstrates workflow mechanics only. It does not claim that sample matchups are official current World Cup fixtures.

