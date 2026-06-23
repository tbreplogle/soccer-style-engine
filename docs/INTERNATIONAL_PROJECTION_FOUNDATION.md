# International Projection Foundation

International projections use a separate data and ratings path from club projections.

National teams have sparse samples, neutral sites, tournament effects, roster volatility, and uneven opponent quality. Club league ratings should not be reused as country-team ratings.

## Data Modes

`true_event_style_historical` means the row uses local StatsBomb Open Data event files. This is historical validation data, not current live event data.

`historical_match_results` means only historical match results are available.

`sparse_free_data_projection` is reserved for optional local Football-Data-style international CSVs.

## Projection Profiles

- `international_score_projection`
- `international_winner_probability`
- `international_total_goals`
- `international_event_style_context`
- `international_model_only`

All profiles expose xG, score probabilities, confidence, risk flags, neutral-site warnings, and data mode. They do not output betting recommendations.

