# Phase 13 Usage

## Club Slate

```powershell
.\.venv\Scripts\python.exe -m src.cli build-club-slate --input data/processed/multi_league_current_match_results.csv --as-of-date 2026-05-25 --league E0 --slate-type historical --max-matches 10
```

## Club Profile Comparison

```powershell
.\.venv\Scripts\python.exe -m src.cli compare-club-profiles --input data/processed/current_match_results.csv --home "Arsenal" --away "Chelsea" --as-of-date 2026-05-25
```

## International Slate

```powershell
.\.venv\Scripts\python.exe -m src.cli build-international-slate --input data/processed/international_match_results.csv --as-of-date 2022-12-01 --team-a "Brazil" --team-b "Morocco" --neutral-site true --competition-context "FIFA World Cup 2022"
```

## International Profile Comparison

```powershell
.\.venv\Scripts\python.exe -m src.cli compare-international-profiles --input data/processed/international_match_results.csv --team-a "Brazil" --team-b "Morocco" --as-of-date 2022-12-01 --neutral-site true
```

Manual matchup CSV samples live under `data/sample/`.

Projection reports are not betting recommendations. Proxy style context is only a free-data proxy unless the data mode explicitly says historical event data.

