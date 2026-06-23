from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from src.config import MATCH_RESULTS_PATH


RESULT_COLUMNS = [
    "match_id",
    "date",
    "competition",
    "season",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "total_goals",
    "result",
    "home_odds_close",
    "draw_odds_close",
    "away_odds_close",
]


def _first_present(row: pd.Series, names: list[str]) -> float | None:
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return None


def normalize_football_data(df: pd.DataFrame, competition: str = "", season: str = "") -> pd.DataFrame:
    """Normalize football-data.co.uk style CSV fields into match results.

    The CSV provider has changed column names over time. This keeps required
    score fields strict and treats shots/cards/odds as optional source columns.
    """
    required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Football-data CSV missing required columns: {sorted(missing)}")

    rows = []
    for idx, row in df.iterrows():
        home_goals = int(row["FTHG"])
        away_goals = int(row["FTAG"])
        result = "H" if home_goals > away_goals else "A" if away_goals > home_goals else "D"
        date = pd.to_datetime(row["Date"], dayfirst=True, errors="coerce")
        rows.append({
            "match_id": f"{competition}_{season}_{idx}".strip("_"),
            "date": date.date().isoformat() if pd.notna(date) else "",
            "competition": competition,
            "season": season,
            "home_team": row["HomeTeam"],
            "away_team": row["AwayTeam"],
            "home_goals": home_goals,
            "away_goals": away_goals,
            "total_goals": home_goals + away_goals,
            "result": result,
            "home_odds_close": _first_present(row, ["B365CH", "PSCH", "B365H", "PSH"]),
            "draw_odds_close": _first_present(row, ["B365CD", "PSCD", "B365D", "PSD"]),
            "away_odds_close": _first_present(row, ["B365CA", "PSCA", "B365A", "PSA"]),
        })
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


class FootballDataLoader:
    def __init__(self, root: str | Path = "data/raw/football-data") -> None:
        self.root = Path(root)

    def load_csv(self, path: str | Path, competition: str = "", season: str = "") -> pd.DataFrame:
        source_path = Path(path)
        if not source_path.is_absolute():
            source_path = self.root / source_path
        raw = pd.read_csv(source_path)
        return normalize_football_data(raw, competition=competition, season=season)

    def build_match_results(
        self,
        csv_paths: Iterable[str | Path],
        output_path: str | Path = MATCH_RESULTS_PATH,
        competition: str = "",
        season: str = "",
    ) -> pd.DataFrame:
        frames = [self.load_csv(path, competition=competition, season=season) for path in csv_paths]
        result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=RESULT_COLUMNS)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
        return result
