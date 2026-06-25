# Phase 25 Terminal Review Example

Review an existing projection file:

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --projection-file outputs/current_international/2026-06-24/current_international_projections.csv
```

Open the generated markdown summary:

```text
outputs/projection_checkpoints/2026-06-24/projection_checkpoint_summary.md
```

Use the summary to answer:

- Are projected totals in a reasonable band?
- Do W/D/L probabilities sum close to 1.0?
- Is the most likely score present?
- Does confidence match data support?
- Are style inputs clearly unavailable when they are missing?
- Are rows labeled real, manual, or sample/demo correctly?
- Did Poisson output build from projected team xG?
- Is there any betting or action language?
