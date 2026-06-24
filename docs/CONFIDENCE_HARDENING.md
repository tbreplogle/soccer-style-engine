# Confidence Hardening

Confidence labels must earn their wording. Phase 14 checks whether High performs better than Medium/Low across seasons and leagues before treating labels as calibrated confidence.

Run:

```powershell
.\.venv\Scripts\python.exe -m src.cli harden-confidence --input data/processed/multi_season_match_results.csv --start-date 2021-08-01 --end-date 2026-05-31
```

If High does not consistently outperform other buckets, the recommended language can soften from `Confidence: High / Medium / Low` to `Data Support: Strong / Moderate / Weak`, remain context-only, or hide labels until calibration improves.

This report separates measured validation from narrative. It does not make unsupported soccer claims and does not treat proxy metrics as true event or tracking style.
