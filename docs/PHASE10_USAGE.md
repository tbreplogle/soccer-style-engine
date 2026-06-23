# Phase 10 Usage

Phase 10 adds projection profiles, confidence scoring, market comparison, and profile diagnostics.

## Run One Projection

```powershell
.\.venv\Scripts\python.exe -m src.cli project-current --input data/processed/current_match_results.csv --home "Arsenal" --away "Chelsea" --as-of-date 2026-05-25 --projection-profile score_projection
```

Available profiles:

- `score_projection`
- `winner_probability`
- `total_goals`
- `market_anchored`
- `model_only`

You can override the profile baseline:

```powershell
.\.venv\Scripts\python.exe -m src.cli project-current --input data/processed/current_match_results.csv --home "Arsenal" --away "Chelsea" --as-of-date 2026-05-25 --projection-profile winner_probability --baseline-mode goals
```

If both `--projection-profile` and `--baseline-mode` are passed, the baseline mode wins.

## Run Profile Diagnostics

```powershell
.\.venv\Scripts\python.exe -m src.cli diagnose-projection-profiles --input data/processed/current_match_results.csv --start-date 2025-10-01 --end-date 2026-05-24
```

Outputs are generated under `outputs/reports/` and should remain ignored:

- `projection_profile_diagnostics_summary.md`
- `projection_profile_diagnostics_results.csv`

## Reading Output

Key Phase 10 fields:

- `projection_profile`: interpretation profile used.
- `baseline_mode_used`: baseline selected after profile and override logic.
- `market_influence_level`: `None`, `Low`, `Medium`, or `High`.
- `confidence_score`: 0 to 100.
- `confidence_label`: `High`, `Medium`, or `Low`.
- `confidence_reasons`: why the confidence score moved.
- `risk_flags`: data or model risks.
- `disagreement_flags`: baseline or model-market disagreement.
- `model_market_gap_summary`: market comparison context.

Market gaps are context only. Proxy adjustments remain disabled by default.

