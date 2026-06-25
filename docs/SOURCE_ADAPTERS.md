# Source Adapters

Phase 21 adds a free current-data adapter foundation under `src/data_sources/`.

## Source Registry

`src/data_sources/source_registry.py` defines expected source capabilities:

- coverage: club, international, World Cup
- field possibilities: xG, lineups, odds, ratings, style proxies, event actions
- source type: CSV, wrapper, scrape, API-like, historical open data
- dependency/network requirements
- reliability and limitation notes

StatsBomb Open Data is marked historical-only.

## Adapter Result Schema

`SourceResult` standardizes source probes:

- status
- rows returned
- fields available/missing
- competitions found
- date range
- currentness, coverage, reliability
- warnings/errors
- raw/cache paths
- data mode label

## Run The Audit

Local-only:

```powershell
.\.venv\Scripts\python.exe -m src.cli audit-free-sources
```

Allow planned network probes:

```powershell
.\.venv\Scripts\python.exe -m src.cli audit-free-sources --allow-network
```

Outputs are generated under:

```text
outputs/source_audits/YYYY-MM-DD/
```

Local and network-permitted audits are separated with suffixes such as `YYYY-MM-DD_local` and `YYYY-MM-DD_network`.

Generated audit files are ignored.

## Add A Source

1. Add source metadata to `source_registry.py`.
2. Add an adapter returning `SourceResult`.
3. Include it in `source_audit.py`.
4. Update recommendations if the source belongs in a use-case stack.
5. Add tests without requiring network.

## Interpret Status

- `success`: local/source probe found usable data.
- `warn`: source exists or is planned, but has limitations.
- `skipped`: intentionally not probed, usually due to no-network or missing optional dependency.
- `fail`: adapter error or unreadable local source.

Local-only mode should not fail just because network data is unavailable.
