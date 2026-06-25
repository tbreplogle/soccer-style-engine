# Phase 21 Free Source Audit Example

Command:

```powershell
.\.venv\Scripts\python.exe -m src.cli audit-free-sources
```

Expected shape:

```text
Source audit output: outputs\source_audits\2026-06-24_local\source_audit_summary.md
Results CSV: outputs\source_audits\2026-06-24_local\source_audit_results.csv
Coverage matrix: outputs\source_audits\2026-06-24_local\source_coverage_matrix.csv
Sources audited: 9
```

Local-only mode should not crash if optional network sources cannot be checked.
