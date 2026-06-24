# Performance Notes

Phase 17 reduces repeated work in daily runs.

Useful flags:

```powershell
--skip-profile-comparison
--profiles score_projection,winner_probability
--reuse-processed-if-fresh
```

Use `--skip-profile-comparison` for faster scheduled runs when a full profile comparison is not needed.

Use `--reuse-processed-if-fresh` with `--skip-download` when the processed file is newer than the relevant raw CSVs.

Timing fields are written to manifests and run logs:

- `download_seconds`
- `normalization_seconds`
- `slate_seconds`
- `audit_seconds`
- `total_duration_seconds`

These are operational timings only. They do not change model meaning.
