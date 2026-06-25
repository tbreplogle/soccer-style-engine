# Current International Source Harvest

Phase 27 adds a source-audit and local-cache harvest layer for current international fixtures, ratings, and basic stats.

The normal workflow now tries real cached/current sources before manual fallback. Manual matchups remain available, but they are not used unless `--manual-matchups` is provided. Sample data still requires `--allow-sample-data`.

## Source Ladder

Fixture ladder:

- local current international fixture cache
- OpenFootball World Cup cache
- FBref World Cup schedule candidate
- ESPN schedule candidate

Rating ladder:

- local current international rating cache
- EloRatings-style local cache
- secondary public Elo table candidate

Stat ladder:

- local basic stat cache
- FBref/ESPN public table candidates
- optional public probes for WhoScored, MarkStats, Scoreroom, and Transfermarkt

Network candidates are audited conservatively. Blocked or unimplemented sources are marked as skipped/blocked instead of being treated as real data.

## Commands

No-network audit:

```powershell
.\.venv\Scripts\python.exe -m src.cli audit-current-international-sources --as-of-date 2026-06-25 --no-network
```

Projection with strict real-data checks:

```powershell
.\.venv\Scripts\python.exe -m src.cli project-current-international --as-of-date 2026-06-25 --no-network --strict-real-data --build-poisson-board
```

## Outputs

Source audit outputs are written under:

```text
outputs/current_international/YYYY-MM-DD/source_audit/
```

Files:

- `source_audit.csv`
- `fixture_coverage.csv`
- `rating_coverage.csv`
- `stat_coverage.csv`
- `match_data_coverage.csv`
- `source_audit_summary.md`

Generated outputs are ignored by git.

## Guardrails

- Current StatsBomb is not used.
- Missing ratings remain missing and are labeled.
- Missing xG/shots fields stay blank.
- Proxy score adjustments remain disabled.
- Model output is projection review context, not betting guidance.
