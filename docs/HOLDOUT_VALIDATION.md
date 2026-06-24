# Holdout Validation

Holdout validation prevents test-season tuning. Phase 14 supports a train, validation, and test split:

```powershell
.\.venv\Scripts\python.exe -m src.cli run-holdout-validation --input data/processed/multi_season_match_results.csv --train-seasons 2122,2223,2324 --validation-season 2425 --test-season 2526
```

The engine chooses candidate defaults from train and validation seasons only. The test season is evaluated afterward to check whether that choice held up.

The report includes the selected default profile, baseline, validation reason, test performance, overfit warning, and one allowed recommendation value. If a selected profile fails on the test season, the report should recommend softening language, changing defaults, disabling confidence labels, or collecting more data.

Style visuals, PassSonar, heat maps, fingerprints, dashboards, and betting picks remain deferred.
