# Automation

Phase 16 adds Windows-friendly automation support without adding a frontend or betting workflow.

PowerShell runner:

```powershell
.\scripts\run_daily_pipeline.ps1 -AsOfDate 2026-05-25 -SeasonCode 2526 -CurrentnessPolicy fail-on-unsafe
```

The script runs:

1. `operational-health-check`
2. `check-data-currentness`
3. `run-daily-pipeline`

Task Scheduler example:

```powershell
.\scripts\task_scheduler_example.ps1
```

The example prints and comments the task registration command. It does not force-create a scheduled task.

There is also an optional GitHub Actions example at `.github/workflows/daily-pipeline-example.yml`. It is manually runnable, uses synthetic/local data, and does not commit generated outputs.

Automation makes the engine easier to run; it does not make outputs betting recommendations. UI, PassSonar, heat maps, style fingerprints, dashboards, and event visuals remain deferred.
