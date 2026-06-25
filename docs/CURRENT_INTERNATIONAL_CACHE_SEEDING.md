# Current International Cache Seeding

Phase 28 adds live-source connector scaffolding and cache seeding for current international fixtures, ratings, and basic stats.

The seed command tries public no-login/no-key sources when network is allowed, writes raw fetch metadata, parses any usable rows, and stores parsed cache files for `audit-current-international-sources` and `project-current-international`.

## Command

No-network cache check:

```powershell
.\.venv\Scripts\python.exe -m src.cli seed-current-international-cache --as-of-date 2026-06-25 --all
```

Allow public source probes:

```powershell
.\.venv\Scripts\python.exe -m src.cli seed-current-international-cache --as-of-date 2026-06-25 --all --allow-network
```

Fixtures and ratings only:

```powershell
.\.venv\Scripts\python.exe -m src.cli seed-current-international-cache --as-of-date 2026-06-25 --fixtures --ratings --allow-network
```

## Cache Layout

Raw fetch cache:

```text
data/source_cache/current_international/raw/
```

Parsed cache:

```text
data/source_cache/current_international/parsed/
```

Compatibility mirrors:

```text
data/source_cache/current_international/fixtures.csv
data/source_cache/current_international/ratings.csv
data/source_cache/current_international/stats.csv
```

These generated cache files are ignored by git.

## Seed Outputs

Run outputs are written to:

```text
outputs/current_international/YYYY-MM-DD/cache_seed/
```

Files:

- `cache_seed_summary.md`
- `fixture_seed_results.csv`
- `rating_seed_results.csv`
- `stat_seed_results.csv`
- `source_fetch_results.csv`
- `parsed_fixture_rows.csv`
- `parsed_rating_rows.csv`
- `parsed_stat_rows.csv`

## Connectors

Fixture connectors:

- OpenFootball-style JSON/CSV
- ESPN public scoreboard payload
- FBref public schedule table

Rating connectors:

- EloRatings-style CSV/HTML
- international-football-style Elo CSV/HTML

Basic stat connectors:

- FBref public team/stat tables

If a source blocks, returns no rows, or has an unexpected layout, the seed result records a status such as `blocked`, `empty`, `not_found`, `parse_error`, `cache_hit`, or `cache_miss`.

## Guardrails

- Current StatsBomb is not used.
- xG and shot fields stay blank unless they exist in the source.
- No login, API key, CAPTCHA, paywall bypass, browser automation, or anti-bot bypass is used.
- Proxy score adjustments remain disabled.
- Outputs are projection review context, not betting guidance.
