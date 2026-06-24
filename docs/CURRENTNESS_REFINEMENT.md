# Currentness Refinement

Phase 17 makes currentness league-level instead of treating the whole slate as stale when one league finishes earlier.

League statuses:

- `current`: recent enough for the requested mode.
- `probably_current`: usable with caveats, often historical/manual mode.
- `season_completed`: expected completed match count is present and no future fixtures remain.
- `offseason`: as-of date is after the season range.
- `stale`: active current/future league data is too old.
- `missing`: required league CSV is absent.
- `unsafe`: no completed matches or required columns are missing.

Expected completed match counts are configurable in `src/operational/currentness.py`. Defaults include `E1 = 552`, `D1 = 306`, and `F1 = 306 or 380`.

Completed leagues are not stale simply because their final match date is earlier than another league. For example, if E1 has 552 completed matches and no future fixtures, it is `season_completed`, not stale.
