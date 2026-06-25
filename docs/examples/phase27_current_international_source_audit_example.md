# Phase 27 Current International Source Audit Example

Run:

```powershell
.\.venv\Scripts\python.exe -m src.cli audit-current-international-sources --as-of-date 2026-06-25 --no-network
```

Expected behavior with no real local cache:

```text
Fixtures found: 0
Real fixture rows: 0
Manual fixture rows: 0
Sample fixture rows: 0
Teams missing ratings: 0
Stats rows: 0
```

The command still writes a source audit folder and summary. It does not fall back to sample fixtures unless `--allow-sample-data` is explicitly supplied.
