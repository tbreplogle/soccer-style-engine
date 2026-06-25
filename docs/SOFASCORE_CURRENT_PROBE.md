# SofaScore Current Probe

Phase 23 adds a conservative SofaScore current-data probe. It is designed to answer what SofaScore can safely provide, not to pretend the source is complete.

## What It Probes

- current football fixtures by date
- scores/results when present in fixture payloads
- basic match statistics by match id
- xG and xGOT if those fields are present
- lineups if available
- player ratings if available in lineup payloads

Missing fields remain null. The adapter does not infer xG, lineups, ratings, or style labels from reputation or fixture-only data.

## Guardrails

- No paid APIs.
- No current StatsBomb.
- No Selenium or browser automation.
- No login, CAPTCHA, paywall, block, or anti-bot bypass.
- No betting recommendations.
- SofaScore data is not true tracking data.
- Proxy score adjustments remain disabled by default.

## Cache Behavior

The probe reads and writes JSON under:

```text
data/source_cache/sofascore/
```

This folder is ignored by git. No-network mode reads existing cache files and skips requests when cache is missing. Allow-network mode makes a small number of polite `urllib` requests, writes cache files, and stops cleanly on blocks or rate limits.

## Commands

Local/cache only:

```bash
python -m src.cli probe-sofascore --as-of-date 2026-06-24 --no-network
```

Allow a conservative network probe:

```bash
python -m src.cli probe-sofascore --as-of-date 2026-06-24 --allow-network --max-matches 5
```

Probe a specific match id:

```bash
python -m src.cli probe-sofascore --match-id 123456 --as-of-date 2026-06-24 --allow-network
```

Outputs are generated under:

```text
outputs/source_probes/sofascore/YYYY-MM-DD/
```

## How To Read Results

- `sofascore_fixture_probe.csv`: parsed fixture rows.
- `sofascore_match_stats_probe.csv`: parsed match-stat rows with nulls for missing fields.
- `sofascore_probe_summary.md`: human-readable availability summary.
- `sofascore_probe_manifest.json`: cache/request/status metadata.

For current international and World Cup workflows, SofaScore fixtures are considered before OpenFootball/TheStatsAPI and before manual fallback. A fixture-only SofaScore row remains low support. Stats can raise support to `high_current_fixture_stats`; stats with xG can raise support to `high_current_fixture_stats_xg`.

