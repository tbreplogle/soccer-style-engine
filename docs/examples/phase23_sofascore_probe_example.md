# Phase 23 SofaScore Probe Example

Local-only command:

```bash
python -m src.cli probe-sofascore --as-of-date 2026-06-24 --no-network
```

Expected behavior with no cache:

- writes a probe summary, empty fixture CSV, empty match-stats CSV, and manifest
- reports zero fixtures and zero stats
- marks cache misses clearly
- does not attempt a network request

Allow-network command:

```bash
python -m src.cli probe-sofascore --as-of-date 2026-06-24 --allow-network --max-matches 5
```

If SofaScore blocks, changes, or omits fields, the probe should warn and leave fields null.

