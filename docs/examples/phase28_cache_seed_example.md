# Phase 28 Cache Seed Example

Run:

```powershell
.\.venv\Scripts\python.exe -m src.cli seed-current-international-cache --as-of-date 2026-06-25 --all --allow-network
```

Then audit:

```powershell
.\.venv\Scripts\python.exe -m src.cli audit-current-international-sources --as-of-date 2026-06-25 --allow-network
```

Then project strictly:

```powershell
.\.venv\Scripts\python.exe -m src.cli project-current-international --as-of-date 2026-06-25 --strict-real-data --build-poisson-board
```

If public sources are blocked or unavailable, the seed step records source statuses and the strict projection fails cleanly instead of using sample/manual data as real current input.
