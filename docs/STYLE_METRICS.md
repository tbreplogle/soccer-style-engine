# Style Metrics

All metrics must come from measurable event data or be null. Event-only proxies are labeled as proxies.

- `possession_pct`: team share of possession-team event rows. This is a proxy until possession duration is modeled from full event timing.
- `field_tilt_pct`: team share of possession events in the attacking final third.
- `avg_possession_length`: average seconds between first and last event in each possession.
- `direct_speed`: mean positive x-axis progression per pass/carry event.
- `passes_completed`: completed StatsBomb pass events.
- `pass_completion_pct`: completed passes divided by total passes.
- `progressive_passes`: completed passes advancing at least 10 StatsBomb x units.
- `progressive_carries`: carries advancing at least 10 StatsBomb x units.
- `final_third_entries`: pass/carry endpoints entering x >= 80 from outside the final third.
- `box_entries`: pass/carry endpoints entering the penalty box from outside.
- `runs_behind_proxy`: through balls or passes into the box. This is not tracking-based run data.
- `fast_attack_count`: possessions no longer than 15 seconds that end in a shot or box entry.
- `counterpressures`: StatsBomb events with `counterpress=true`.
- `pressures`: StatsBomb pressure events.
- `high_regains`: ball recoveries/interceptions in the attacking 40 percent of the pitch.
- `ppda_proxy`: opponent passes divided by high defensive actions.
- `defensive_block_height`: median x location of defensive events; with 360, median visible line height can replace it.
- `compactness`, `opponent_players_between_ball_and_goal`, `pass_options_visible`, `central_density`, `defensive_block_depth`, `width_in_possession`, `depth_in_possession`: 360-derived approximations only. They stay null when 360 is missing.
- `set_piece_xg_for`, `set_piece_xg_against`: StatsBomb shot xG from corner/free-kick/throw/set-piece play patterns.

Coordinate assumption: StatsBomb 120x80 coordinates are treated as attacking left-to-right after a conservative team-level shot-location orientation check.
