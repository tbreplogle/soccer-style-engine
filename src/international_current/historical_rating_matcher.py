from __future__ import annotations

from typing import Any

import pandas as pd

from src.international_current.team_name_normalization import normalize_team_name


MATCHED_HISTORICAL_COLUMNS = [
    "match_date",
    "competition",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "neutral_site",
    "home_rating",
    "away_rating",
    "home_rating_snapshot_date",
    "away_rating_snapshot_date",
    "rating_snapshot_age_days_home",
    "rating_snapshot_age_days_away",
    "rating_match_status",
    "rating_match_warning",
]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=MATCHED_HISTORICAL_COLUMNS)


def _match_one(team: str, match_date: pd.Timestamp, snapshots: pd.DataFrame, max_snapshot_age_days: int) -> tuple[float | None, str, int | None, str]:
    normalized = normalize_team_name(team).normalized_name
    work = snapshots[
        (snapshots["normalized_team_name"].astype(str) == normalized)
        & (pd.to_datetime(snapshots["snapshot_date"], errors="coerce") <= match_date)
    ].copy()
    if work.empty:
        return None, "", None, "missing"
    work["_snapshot_date"] = pd.to_datetime(work["snapshot_date"], errors="coerce")
    work = work.sort_values("_snapshot_date")
    row = work.iloc[-1]
    age = int((match_date - row["_snapshot_date"]).days)
    if age > max_snapshot_age_days:
        return float(row["rating"]), str(row["snapshot_date"])[:10], age, "too_old"
    return float(row["rating"]), str(row["snapshot_date"])[:10], age, "matched"


def attach_historical_ratings(
    results: pd.DataFrame,
    snapshots: pd.DataFrame,
    *,
    max_snapshot_age_days: int = 365,
) -> pd.DataFrame:
    if results.empty:
        return _empty()
    if snapshots.empty:
        out = results.copy()
        for column in MATCHED_HISTORICAL_COLUMNS:
            if column not in out.columns:
                out[column] = ""
        out["rating_match_status"] = "both_ratings_missing"
        out["rating_match_warning"] = "No historical rating snapshots available on or before match date."
        return out[MATCHED_HISTORICAL_COLUMNS]

    rows: list[dict[str, Any]] = []
    for _, match in results.iterrows():
        match_date = pd.to_datetime(match.get("match_date"), errors="coerce")
        if pd.isna(match_date):
            continue
        home_rating, home_date, home_age, home_status = _match_one(str(match.get("home_team", "")), match_date, snapshots, max_snapshot_age_days)
        away_rating, away_date, away_age, away_status = _match_one(str(match.get("away_team", "")), match_date, snapshots, max_snapshot_age_days)
        if home_status == "matched" and away_status == "matched":
            status = "both_ratings_matched"
            warning = ""
        elif home_status == "too_old" or away_status == "too_old":
            status = "snapshot_too_old"
            warning = f"Latest available snapshot exceeds max age of {max_snapshot_age_days} days."
        elif home_status == "missing" and away_status == "missing":
            status = "both_ratings_missing"
            warning = "Both teams missing historical rating snapshots on or before match date."
        elif home_status == "missing":
            status = "home_rating_missing"
            warning = "Home team missing historical rating snapshot on or before match date."
        else:
            status = "away_rating_missing"
            warning = "Away team missing historical rating snapshot on or before match date."
        rows.append({
            "match_date": str(match.get("match_date", ""))[:10],
            "competition": match.get("competition", ""),
            "home_team": match.get("home_team", ""),
            "away_team": match.get("away_team", ""),
            "home_goals": match.get("home_goals"),
            "away_goals": match.get("away_goals"),
            "neutral_site": match.get("neutral_site", "true"),
            "home_rating": home_rating,
            "away_rating": away_rating,
            "home_rating_snapshot_date": home_date,
            "away_rating_snapshot_date": away_date,
            "rating_snapshot_age_days_home": home_age,
            "rating_snapshot_age_days_away": away_age,
            "rating_match_status": status,
            "rating_match_warning": warning,
        })
    return pd.DataFrame(rows, columns=MATCHED_HISTORICAL_COLUMNS)
