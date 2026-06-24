# Phase 19 Run Today Example

Command:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-today --as-of-date 2026-05-25 --skip-download --max-matches 5
```

Expected shape:

```text
Run today status: success_with_warnings
Run dir: outputs\runs\2026-05-25
Viewer: outputs\viewer\index.html
Viewer safety scan: pass
```

Warnings can include completed-season notes, skipped download, or reused processed data.

