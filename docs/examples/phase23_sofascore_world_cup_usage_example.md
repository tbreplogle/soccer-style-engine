# Phase 23 SofaScore World Cup Usage Example

Workflow:

```bash
python -m src.cli probe-sofascore --as-of-date 2026-06-24 --competition "FIFA World Cup" --no-network
python -m src.cli audit-current-international --as-of-date 2026-06-24 --no-network
python -m src.cli build-current-international-slate --manual-matchups data/sample/current_international_matchups.csv --as-of-date 2026-06-24 --no-network
```

If SofaScore cached fixtures exist, the current international slate can include them before manual fallback. If only manual rows exist, support remains low and the projection report should say so.

