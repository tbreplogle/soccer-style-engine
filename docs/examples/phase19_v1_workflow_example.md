# Phase 19 V1 Workflow Example

Recommended local flow:

```powershell
.\scripts\test_quick.ps1
.\scripts\run_today.ps1 -SkipDownload -MaxMatches 5
.\scripts\open_viewer.ps1
```

For a data refresh, run `.\scripts\run_today.ps1 -Download`.

Before commit or merge:

```powershell
.\scripts\test_full.ps1
git status --short
git status --ignored --short
git diff --check
```

Generated outputs stay ignored. Commit source, tests, scripts, docs, examples, and sample fixtures only.
