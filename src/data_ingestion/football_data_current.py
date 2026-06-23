from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


CURRENT_RESULT_COLUMNS = [
    "match_id",
    "date",
    "league",
    "season",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "total_goals",
    "result",
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
    "home_corners",
    "away_corners",
    "home_fouls",
    "away_fouls",
    "home_yellow_cards",
    "away_yellow_cards",
    "home_red_cards",
    "away_red_cards",
    "home_odds_close",
    "draw_odds_close",
    "away_odds_close",
    "over_2_5_odds_close",
    "under_2_5_odds_close",
    "data_source",
    "data_quality_flags",
]


def _value(row: pd.Series, names: list[str]) -> object:
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return pd.NA


def _num(row: pd.Series, names: list[str]) -> float | pd.NA:
    value = _value(row, names)
    return pd.to_numeric(value, errors="coerce") if pd.notna(value) else pd.NA


def _result(home_goals: object, away_goals: object, fallback: object = pd.NA) -> object:
    if pd.notna(fallback):
        return fallback
    if pd.isna(home_goals) or pd.isna(away_goals):
        return pd.NA
    if home_goals > away_goals:
        return "H"
    if away_goals > home_goals:
        return "A"
    return "D"


def normalize_current_football_data(
    raw: pd.DataFrame,
    league: str = "",
    season: str = "",
    data_source: str = "local_csv",
) -> pd.DataFrame:
    required = {"Date", "HomeTeam", "AwayTeam"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Football-Data current CSV missing required columns: {sorted(missing)}")

    rows = []
    for idx, row in raw.iterrows():
        home_goals = _num(row, ["FTHG"])
        away_goals = _num(row, ["FTAG"])
        date = pd.to_datetime(row["Date"], dayfirst=True, errors="coerce")
        flags = []
        for group, cols in {
            "missing_shots": ["HS", "AS"],
            "missing_sot": ["HST", "AST"],
            "missing_corners": ["HC", "AC"],
            "missing_odds": ["B365H", "PSH", "AvgH", "MaxH"],
        }.items():
            if not any(col in raw.columns for col in cols):
                flags.append(group)
        rows.append({
            "match_id": f"{league}_{season}_{idx}".strip("_"),
            "date": date.date().isoformat() if pd.notna(date) else "",
            "league": league or str(row.get("Div", "")),
            "season": season,
            "home_team": row["HomeTeam"],
            "away_team": row["AwayTeam"],
            "home_goals": home_goals,
            "away_goals": away_goals,
            "total_goals": home_goals + away_goals if pd.notna(home_goals) and pd.notna(away_goals) else pd.NA,
            "result": _result(home_goals, away_goals, row.get("FTR", pd.NA)),
            "home_shots": _num(row, ["HS"]),
            "away_shots": _num(row, ["AS"]),
            "home_shots_on_target": _num(row, ["HST"]),
            "away_shots_on_target": _num(row, ["AST"]),
            "home_corners": _num(row, ["HC"]),
            "away_corners": _num(row, ["AC"]),
            "home_fouls": _num(row, ["HF"]),
            "away_fouls": _num(row, ["AF"]),
            "home_yellow_cards": _num(row, ["HY"]),
            "away_yellow_cards": _num(row, ["AY"]),
            "home_red_cards": _num(row, ["HR"]),
            "away_red_cards": _num(row, ["AR"]),
            "home_odds_close": _num(row, ["B365H", "PSH", "MaxH", "AvgH"]),
            "draw_odds_close": _num(row, ["B365D", "PSD", "MaxD", "AvgD"]),
            "away_odds_close": _num(row, ["B365A", "PSA", "MaxA", "AvgA"]),
            "over_2_5_odds_close": _num(row, ["B365>2.5", "Max>2.5", "Avg>2.5"]),
            "under_2_5_odds_close": _num(row, ["B365<2.5", "Max<2.5", "Avg<2.5"]),
            "data_source": data_source,
            "data_quality_flags": "|".join(flags) if flags else "complete_basic_match_stats",
        })
    return pd.DataFrame(rows, columns=CURRENT_RESULT_COLUMNS)


def load_current_csv(path: str | Path, league: str = "", season: str = "") -> pd.DataFrame:
    source = Path(path)
    raw = pd.read_csv(source)
    return normalize_current_football_data(raw, league=league, season=season, data_source=str(source))


def load_current_folder(folder: str | Path, league: str = "", season: str = "") -> pd.DataFrame:
    root = Path(folder)
    files = sorted(root.glob("*.csv"))
    frames = [load_current_csv(path, league=league, season=season) for path in files]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=CURRENT_RESULT_COLUMNS)


def load_current_csv_url(csv_url: str, league: str = "", season: str = "") -> pd.DataFrame:
    raw = pd.read_csv(csv_url)
    return normalize_current_football_data(raw, league=league, season=season, data_source=csv_url)


def normalize_current_inputs(
    input_path: str | Path | None = None,
    csv_url: str | None = None,
    output_path: str | Path | None = None,
    league: str = "",
    season: str = "",
) -> pd.DataFrame:
    if csv_url:
        result = load_current_csv_url(csv_url, league=league, season=season)
    elif input_path is None:
        raise ValueError("Provide --input or --csv-url.")
    else:
        path = Path(input_path)
        result = load_current_folder(path, league=league, season=season) if path.is_dir() else load_current_csv(path, league=league, season=season)
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
    return result
