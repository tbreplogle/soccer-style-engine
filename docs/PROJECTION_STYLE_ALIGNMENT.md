# Projection Style Alignment

The final product goal is better score projections.

The project thesis is that score projections should improve when matchup style is understood: buildup versus press, low block versus possession, transition threat versus high line, directness versus defensive recovery, territory, chance creation style, and matchup-specific pressure points.

Phase 24 is not that final style-aware projection engine. It is the reliable fixture + rating backbone that lets current World Cup and international projections run today while clearly labeling what is still missing.

## Why Backbone First

V1 proved the free workflow can run, validate, and report without paid data. Phases 21-23 tested current data-source options and showed that safe SofaScore probing currently receives HTTP 403, so the current workflow cannot depend on it.

Phase 24 solves a practical gap: it can produce current international score projections from known fixtures and national-team ratings, using local/static sources that do not require signup, API keys, browser automation, or paid feeds.

## What Phase 24 Does Not Solve

- It does not create style-aware matchup adjustments.
- It does not use current event data, xG, lineups, injuries, or tracking.
- It does not treat Elo/rating differences as style advantages.
- It does not use current StatsBomb.
- It does not produce betting recommendations.

Elo/rating-only projections are a temporary baseline and fallback. Fixture + rating support is useful for current score projection scaffolding, but it is not style-aware projection yet.

## Data Still Needed

True style-aware score projection needs reliable current or historically validated inputs for chance creation, pressure, buildup, directness, defensive block behavior, transition exposure, field tilt, xG, lineups, and matchup-specific adjustments.
Those future style-aware matchup inputs are not present in the Phase 24 fixture + rating backbone.

## Future Path

1. reliable current fixtures and ratings
2. current projection output that works today
3. current match stats/xG enrichment if safely available
4. style proxy layer from available stats
5. matchup-style adjustment testing
6. historical StatsBomb validation
7. style-aware score projection reports
8. optional visual layers only after projections prove useful

## Phase 25 Checkpoint

Phase 25 reviews projection outputs before adding style adjustments. It checks projection totals, score/probability shape, confidence, data support, missing values, warning language, and style-input availability.

The checkpoint makes the baseline explicit: current World Cup/international outputs can be rating-aware and fixture-aware, but style-aware adjustments remain inactive unless measurable style inputs are present.

The intended output path is style-aware projected xG into a Poisson probability board. Future style-aware matchup logic should improve the projected home xG and away xG inputs; Poisson then turns those xG values into 1X2, totals, BTTS, clean sheet, and correct-score probabilities.

Sample fixtures are demo-only and must be explicitly enabled. Manual fixtures are user supplied and should stay labeled as such.

## Phase 26 Viewer Polish

Phase 26 does not add style-aware xG adjustment. It makes the existing checkpoint Poisson outputs easier to inspect in the static viewer.

The board page reads generated checkpoint CSV/Markdown files and shows projected team xG, probability output, model-implied American odds, totals, BTTS, clean sheets, correct scores, and source/support warnings. It keeps style inputs marked unavailable when the row is rating-only or fixture-only.

This prepares the review surface for future style-aware xG work: first make projected xG and probability outputs understandable, then test whether measured style inputs improve those xG inputs.
## Phase 32 Baseline Calibration Note

The current international board remains a rating-based baseline. Fixture deduplication and historical rating snapshot matching make the baseline cleaner and more measurable, but they do not create style-aware xG.

Style adjustments should be layered only after the baseline has enough leakage-safe calibration evidence. The highest-value missing inputs are shots for/against, xG for/against, open-play and set-piece xG, possession or field-tilt proxies, directness/transition proxies, discipline, and verified absence/injury context.

Current StatsBomb is not used as live data, proxy adjustments remain disabled by default, and generated probability outputs are not betting recommendations.

## Phase 33 Calibration Organization And Tuning

Phase 33 preserves calibration evidence by writing every calibration attempt to a unique run folder:

```text
outputs/calibration/YYYY-MM-DD/<data_source>/<run_id>/
```

This prevents one calibration run from overwriting another. The date folder keeps `latest_manifest.json`, each data source keeps its own `latest_manifest.json`, and `calibration_run_index.csv` summarizes runs, leakage status, core metrics, recommendation labels, tuning status, and output paths.

Baseline tuning remains diagnostic-only. It can compare conservative rating-baseline parameter candidates and write a `candidate_model_config.json` for preview, but it does not change production defaults. Candidate preview output compares baseline versus candidate xG/probabilities under `outputs/current_international/YYYY-MM-DD/candidate_preview/`.

This is still not true style alignment. Ratings are strength priors, not event/tracking style evidence. Any future style layer must remain traceable to measurable style inputs and must beat the organized baseline on leakage-safe validation.
