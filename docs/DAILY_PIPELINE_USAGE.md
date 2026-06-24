# Daily Pipeline Usage

Run a daily club slate:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-daily-pipeline --as-of-date YYYY-MM-DD
```

Useful options:

- `--skip-download` uses local Football-Data CSVs only.
- `--leagues E0,E1,SP1,D1,I1,F1` controls included leagues.
- `--slate-type auto|future|historical|manual` controls matchup selection.
- `--max-matches 20` limits the slate size.
- `--manual-club-matchups data/sample/manual_club_matchups.csv` runs named club matchups.
- `--include-international` adds international output if input exists.
- `--run-quick-audit` writes a leakage audit summary into the run folder.

Run outputs include:

- `club_slate_report.md`
- `club_slate_projections.csv`
- `projection_profile_comparison.md`
- `projection_profile_comparison.csv`
- `run_manifest.json`
- `run_summary.md`

The manifest records inputs, defaults, guardrails, git metadata, row counts, generated files, and warnings. The run summary is the human-readable overview.

The daily pipeline is not a betting system. Confidence is Data Support / Risk Context, market gaps are diagnostics, and proxy style context is not true tracking/event style for current free data.
