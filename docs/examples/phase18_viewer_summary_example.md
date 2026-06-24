# Phase 18 Viewer Summary Example

Example command:

```powershell
.\.venv\Scripts\python.exe -m src.cli build-report-viewer --runs-root outputs/runs --output-dir outputs/viewer
```

Example output:

```text
Viewer output: outputs/viewer/index.html
Runs included: 1
Safety scan status: pass
```

The viewer index links to one static detail page per run. Detail pages include run summary text, warning groups, currentness status, club slate tables, international slate tables when present, and profile comparison tables when present.

