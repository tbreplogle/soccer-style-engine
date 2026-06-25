# Phase 22 Current International Audit Example

Command:

```bash
python -m src.cli audit-current-international --as-of-date 2026-06-24 --no-network
```

Expected behavior:

- Local cache adapters report success only when cache files exist.
- Network-backed adapters skip or warn without failing tests.
- Current StatsBomb remains excluded.
- Fixture-only sources are labeled as schedule/results coverage, not style coverage.

