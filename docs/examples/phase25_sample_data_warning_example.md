# Phase 25 Sample Data Warning Example

Default no-network current international checkpoint:

```powershell
.\.venv\Scripts\python.exe -m src.cli projection-results-checkpoint --as-of-date 2026-06-24 --run-current-international --no-network
```

If no real cache or manual matchup file exists, the command reports zero rows and warns:

```text
No real current fixture source available. Provide --manual-matchups or run with --allow-sample-data for demo output.
```

Demo sample output requires:

```powershell
--allow-sample-data
```

Sample rows are labeled:

- `is_sample_data=true`
- `source_tier=sample`
- `reliability_status=sample_only`
- `data_support_level=sample_demo_only`
