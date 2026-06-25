# V1 Release Notes

Version: `0.1.0-free-v1`

Free v1 is a local, explainable soccer projection workflow. It is designed to be boring, repeatable, and honest about what the data supports.

## What V1 Can Do

- Normalize Football-Data-style CSVs for current club workflows.
- Use sample/open StatsBomb event data where local files are available.
- Build conservative club slate projections.
- Build conservative international projections when international data is supplied.
- Compare projection profiles and market/context baselines.
- Run currentness checks, season sanity checks, leakage audits, calibration diagnostics, and validation tests.
- Write run manifests, run summaries, run logs, projections, and report files.
- Build a lightweight static HTML viewer from generated run outputs.
- Run quick everyday tests and full validation tests.

## What V1 Cannot Do Yet

- It does not provide betting recommendations.
- It does not guarantee outcomes.
- It does not model injuries, lineups, transfers, roster strength, or live team news.
- It does not consume a live xG feed.
- It does not provide full PassSonar, heat maps, style fingerprints, dashboards, or event visuals.
- It does not turn free proxy metrics into true tracking/event style.

## Supported Workflows

- `.\scripts\run_today.ps1`
- `.\scripts\validate_v1.ps1`
- `.\scripts\test_quick.ps1`
- `.\scripts\test_full.ps1`
- `.\scripts\build_viewer.ps1`
- `.\scripts\open_viewer.ps1`
- `.\.venv\Scripts\python.exe -m src.cli run-today`
- `.\.venv\Scripts\python.exe -m src.cli validate-v1`

## Supported Data Sources

- Football-Data-style CSVs for current club match-level data.
- StatsBomb Open Data files when present locally for historical event-style workflows.
- Sample fixtures in `data/sample/` for tests and examples.

## Projection Status

Club projection status: v1-ready as a conservative local workflow with currentness and validation context.

International projection status: foundation-ready, but sparse and historical unless current international data is supplied.

## Viewer Status

The static viewer is v1-ready as a local report reader. It reads generated outputs and does not recompute projections.

## No-Betting Guardrail

V1 intentionally avoids wagering advice. Market gaps are diagnostic context only, and Data Support / Risk Context is not certainty.

## Known Limitations

See `docs/V1_LIMITATIONS.md`.

## Next Roadmap After V1

- Improve speed of the full validation suite.
- Add richer data-source status reporting.
- Calibrate support labels further.
- Add roster/injury inputs only when reliable sources exist.
- Explore style visuals after operational output remains stable.

## Optional Tagging Later

If desired after review, a human can tag the release manually:

```powershell
git tag v0.1.0-free-v1
git push origin v0.1.0-free-v1
```

Do not create the tag until the release branch is reviewed.
