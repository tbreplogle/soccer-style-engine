# Phase 20 V1 Validation Example

```powershell
.\.venv\Scripts\python.exe -m src.cli validate-v1
```

Expected shape:

```text
v1_status: pass
checks:
- version: pass - version=0.1.0-free-v1
- operational_health_check: pass - health_status=pass
warnings:
- None
recommended fixes:
- None
```

If the status is `warn`, inspect the warning and decide whether it is acceptable for local-only release validation.

