# Phase 17 Completed League Not Stale Example

Example only.

```text
| league | status | completed | expected | pct | latest_completed | finished |
| --- | --- | --- | --- | --- | --- | --- |
| E1 | season_completed | 552 | 552 | 1.0 | 2026-05-02 | True |
```

E1 can finish earlier than EPL and still be complete. It should not be reported as stale when its expected match count is present and no future fixtures remain.
