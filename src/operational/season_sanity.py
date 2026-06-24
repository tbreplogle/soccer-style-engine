from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


def season_code_date_range(season_code: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    code = str(season_code).strip()
    if len(code) != 4 or not code.isdigit():
        return None
    start_year = 2000 + int(code[:2])
    end_year = 2000 + int(code[2:])
    if end_year != start_year + 1:
        return None
    return pd.Timestamp(date(start_year, 7, 1)), pd.Timestamp(date(end_year, 6, 30))


def check_season_sanity(season_code: str, as_of_date: str, historical_mode: bool = False) -> dict[str, Any]:
    parsed = pd.to_datetime(as_of_date, errors="coerce")
    warnings: list[str] = []
    if pd.isna(parsed):
        return {
            "season_sanity_status": "unsafe",
            "expected_date_range": None,
            "as_of_date": as_of_date,
            "warnings": ["as_of_date could not be parsed."],
            "recommended_action": "Fix the run date before running projections.",
        }
    expected = season_code_date_range(season_code)
    if expected is None:
        return {
            "season_sanity_status": "unsafe",
            "expected_date_range": None,
            "as_of_date": parsed.date().isoformat(),
            "warnings": [f"Season code {season_code} is not a recognized two-year code."],
            "recommended_action": "Use a Football-Data season code such as 2526 or 2425.",
        }
    start, end = expected
    status = "ok"
    action = "Season/date pairing looks plausible."
    if parsed < start or parsed > end:
        status = "warning" if historical_mode else "warning"
        warnings.append(f"as_of_date {parsed.date().isoformat()} is outside season {season_code} ({start.date()} to {end.date()}).")
        action = "Use --historical-mode if this is intentional, or choose the season code matching the run date."
    if parsed < pd.Timestamp("2000-01-01") or parsed > pd.Timestamp("2100-01-01"):
        status = "unsafe"
        warnings.append("as_of_date is outside the supported sanity-check range.")
        action = "Fix the run date before running projections."
    if historical_mode and warnings and status != "unsafe":
        warnings.append("Historical mode allows this season/date mismatch but reports should show the warning.")
        action = "Proceed only as historical/offseason validation context."
    return {
        "season_sanity_status": status,
        "expected_date_range": {"start": start.date().isoformat(), "end": end.date().isoformat()},
        "as_of_date": parsed.date().isoformat(),
        "warnings": warnings,
        "recommended_action": action,
    }
