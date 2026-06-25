# Phase 22 Current World Cup Workflow Example

Command:

```bash
python -m src.cli project-current-international --manual-matchups data/sample/current_international_matchups.csv --as-of-date 2026-06-24 --no-network --max-matches 10
```

Expected output files:

- `current_international_source_summary.md`
- `current_international_slate.csv`
- `current_international_projection_report.md`
- `current_international_projections.csv`
- `current_international_manifest.json`

The projection report should show low support when only manual fixture data is available.

