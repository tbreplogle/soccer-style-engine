# Season Sanity

Season sanity maps Football-Data season codes to rough date windows:

- `2526`: 2025-07-01 to 2026-06-30
- `2425`: 2024-07-01 to 2025-06-30
- `2324`: 2023-07-01 to 2024-06-30

Run:

```powershell
.\.venv\Scripts\python.exe -m src.cli check-season-sanity --season-code 2526 --as-of-date 2026-05-25
```

Use `--historical-mode` when the date/season mismatch is intentional. Historical mode warns instead of hiding the mismatch.

Season sanity is a guardrail for automation. It does not change model projections and it does not create betting guidance.
