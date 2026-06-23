# Free Current Data Plan

Phase 6 keeps the project free by using Football-Data-style current results, match stats, and odds where available. This data can support a current baseline and honest proxy metrics, but it does not contain full event locations, tracking, off-ball movement, or shape.

## Data Sources

- Local CSV files under `data/raw/football-data/`
- Optional one-off CSV URL loading for Football-Data-style files
- Synthetic fixtures under `data/sample/football-data/` for tests

Raw current data and generated outputs are ignored by git. Synthetic sample fixtures are committed.

## Data Modes

- `true_event_style`: StatsBomb/event-location style metrics.
- `free_proxy_style`: Football-Data/basic-stat proxies.
- `market_baseline_only`: market or results baseline when style proxy evidence is too thin.

## Why Proxies

Shots, shots on target, corners, fouls, cards, goals, and odds can hint at pressure, tempo, volatility, and dominance. They cannot prove true possession structure, off-ball runs, pressing traps, line height, compactness, or direct passing routes. Phase 6 labels every style output as a proxy.
