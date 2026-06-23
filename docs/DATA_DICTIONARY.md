# Data Dictionary

## `data/processed/match_results.csv`

- `match_id`: stable local match identifier.
- `date`: match date.
- `competition`: competition name/code.
- `season`: season label.
- `home_team`, `away_team`: participating teams.
- `home_goals`, `away_goals`: full-time goals.
- `total_goals`: full-time total goals.
- `result`: `H`, `D`, or `A`.
- `home_odds_close`, `draw_odds_close`, `away_odds_close`: closing odds when present in source CSV.

## `data/processed/team_match_style_log.csv`

One row per team per match.

- `match_id`, `date`, `competition`, `season`: match context.
- `team`, `opponent`, `is_home`: team context.
- `goals_for`, `goals_against`, `result`: observed score outcome.
- `possession_pct`, `field_tilt_pct`, `avg_possession_length`, `direct_speed`: possession/territory/tempo.
- `passes_completed`, `pass_completion_pct`: passing volume and completion share.
- `progressive_passes`, `progressive_carries`, `final_third_entries`, `box_entries`: progression.
- `runs_behind_proxy`, `fast_attack_count`: event-only vertical threat proxies.
- `shots`, `shots_on_target`, `xg_for`, `xg_against`: chance creation/prevention.
- `counterpressures`, `pressures`, `high_regains`, `ppda_proxy`: pressing proxies.
- `turnovers_own_third`, `turnovers_middle_third`: ball-security risks.
- `defensive_block_height`, `compactness`, `opponent_players_between_ball_and_goal`, `pass_options_visible`, `central_density`, `defensive_block_depth`, `width_in_possession`, `depth_in_possession`: shape/context fields. Some are null without 360.
- `set_piece_xg_for`, `set_piece_xg_against`: set-piece chance quality.
- `data_quality_flag`: `event_only` or `event_plus_360`.

## `outputs/projections/match_projection.csv`

- Base xG fields expose the historical-strength estimate.
- Style adjustment fields expose the capped matchup adjustment.
- Final xG fields drive the independent Poisson distribution.
- Probability fields are model outputs, not betting advice.
