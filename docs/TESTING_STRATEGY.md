# Testing Strategy

Phase 19 splits tests into quick and full validation workflows.

## Markers

- `quick`: lightweight everyday development tests.
- `slow`: heavier validation or workflow tests.
- `integration`: tests that exercise multiple subsystems together.
- `real_data_optional`: tests that can use optional real-data fixtures if present.

## Everyday Development

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not slow"
```

This should be the default inner-loop command.

## Full Validation

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run this before commit or merge.

Slow tests are intentional. They cover calibration, operational runs, report generation, and cross-module workflows.

Normal tests should not require network or raw data.
