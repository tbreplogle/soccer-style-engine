# Phase 24 Fixture Rating Workflow Example

```bash
python -m src.cli audit-current-international
python -m src.cli build-worldcup-backbone --as-of-date 2026-06-24 --no-network
python -m src.cli project-current-international --as-of-date 2026-06-24 --no-network --max-matches 10
```

If fixture and rating samples are present, the workflow should produce baseline score projections. If ratings are missing, support drops and warnings explain the missing evidence.

