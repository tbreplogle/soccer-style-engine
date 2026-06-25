from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_sources.source_result import SourceResult


EXPECTED_FIELDS = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]
STATS_FIELDS = ["HS", "AS", "HST", "AST", "HC", "AC"]
ODDS_PREFIXES = ("B365", "BW", "IW", "PS", "WH", "VC", "Max", "Avg")


def audit_football_data(raw_dir: str | Path = "data/raw/football-data") -> SourceResult:
    root = Path(raw_dir)
    if not root.exists():
        return SourceResult(
            source_name="football_data",
            status="warn",
            fields_missing=EXPECTED_FIELDS,
            currentness_status="missing",
            coverage_status="missing_local_raw_dir",
            reliability_status="local_files_missing",
            warnings=[f"{root} does not exist; place Football-Data CSVs locally or run download workflow."],
            raw_path=str(root),
            data_mode="unavailable",
        )
    csvs = sorted(root.glob("*.csv"))
    if not csvs:
        return SourceResult(
            source_name="football_data",
            status="warn",
            fields_missing=EXPECTED_FIELDS,
            currentness_status="missing",
            coverage_status="no_csv_files",
            reliability_status="local_files_missing",
            warnings=[f"No Football-Data CSVs found in {root}."],
            raw_path=str(root),
            data_mode="unavailable",
        )
    frames = []
    fields: set[str] = set()
    competitions: set[str] = set()
    errors: list[str] = []
    for path in csvs:
        try:
            frame = pd.read_csv(path)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        fields.update(map(str, frame.columns))
        competitions.add(path.stem.split("_")[0])
        if "Date" in frame:
            frame = frame.copy()
            frame["__date"] = pd.to_datetime(frame["Date"], errors="coerce", dayfirst=True)
        frames.append(frame)
    if not frames:
        return SourceResult(
            source_name="football_data",
            status="fail",
            fields_missing=EXPECTED_FIELDS,
            currentness_status="unreadable",
            coverage_status="unreadable_csvs",
            reliability_status="fail",
            errors=errors,
            raw_path=str(root),
            data_mode="unavailable",
        )
    combined = pd.concat(frames, ignore_index=True, sort=False)
    dates = combined["__date"].dropna() if "__date" in combined else pd.Series(dtype="datetime64[ns]")
    missing = [field for field in EXPECTED_FIELDS if field not in fields]
    available_stats = [field for field in STATS_FIELDS if field in fields]
    available_odds = [field for field in fields if field.startswith(ODDS_PREFIXES)]
    warnings = []
    if missing:
        warnings.append(f"Missing expected Football-Data fields: {', '.join(missing)}")
    if not available_stats:
        warnings.append("No match-stat fields found; projection style proxies may be limited.")
    if not available_odds:
        warnings.append("No odds fields found; market comparison coverage may be limited.")
    return SourceResult(
        source_name="football_data",
        status="warn" if warnings or errors else "success",
        rows_returned=int(len(combined)),
        fields_available=sorted(fields),
        fields_missing=missing,
        competitions_found=sorted(competitions),
        date_min=str(dates.min().date()) if not dates.empty else "",
        date_max=str(dates.max().date()) if not dates.empty else "",
        currentness_status="available_local",
        coverage_status="club_results_and_fixtures",
        reliability_status="local_csv_available",
        warnings=warnings,
        errors=errors,
        raw_path=str(root),
        data_mode="current_results_stats",
    )
