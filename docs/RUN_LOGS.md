# Run Logs

Daily pipeline runs append to generated logs:

- `outputs/run_logs/daily_pipeline_log.csv`
- `outputs/run_logs/daily_pipeline_log.jsonl`

Each row records run date, run status, currentness status, season sanity status, leagues, row count, slate type, output count, warning count, error message, total duration, and phase timings.

Timing fields include download, normalization, slate, audit, and total duration seconds.

These logs are generated operational artifacts and remain ignored by git.

Use logs to spot failed automation, stale data runs, or repeated warnings. Do not treat log success as a betting signal or model-quality guarantee.
