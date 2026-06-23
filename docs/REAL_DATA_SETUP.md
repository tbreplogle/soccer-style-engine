# Real Data Setup

Phase 5 validates the style engine against real StatsBomb Open Data stored locally. The project does not download raw data at runtime.

## Get StatsBomb Open Data

StatsBomb Open Data is published publicly by StatsBomb. Download or clone the open-data repository from StatsBomb's public GitHub project, then place the files in this repo under:

```text
data/raw/statsbomb-open-data/
```

## Expected Folder Structure

```text
data/raw/statsbomb-open-data/
  competitions.json
  matches/
    {competition_id}/
      {season_id}.json
  events/
    {match_id}.json
  lineups/
    {match_id}.json
  three-sixty/
    {match_id}.json
```

The `three-sixty/` folder is optional and only exists for matches where StatsBomb 360 data is available.

## Git Hygiene

Raw data is intentionally ignored by git via `data/raw/*`. Keep raw StatsBomb files local and do not commit them. The repo keeps `data/raw/.gitkeep` only so the expected directory exists.

Generated validation reports under `outputs/reports/` are also ignored. They can be regenerated with the CLI.

## Run Validation

```powershell
.\.venv\Scripts\python.exe -m src.cli validate-real-data --statsbomb-root data/raw/statsbomb-open-data --competition-id 43 --season-id 106 --max-matches 10
```

If `--competition-id` and `--season-id` are omitted, the validator picks the first available competition/season from `competitions.json`.
