from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import pandas as pd

from src.data_ingestion.football_data_current import CURRENT_RESULT_COLUMNS, normalize_current_football_data


FOOTBALL_DATA_BASE_URL = "https://www.football-data.co.uk/mmz4281"
LEAGUE_NAMES = {
    "E0": "EPL",
    "E1": "Championship",
    "SP1": "La Liga",
    "D1": "Bundesliga",
    "I1": "Serie A",
    "F1": "Ligue 1",
}
SEASON_LABELS = {
    "2526": "2025-2026",
    "2425": "2024-2025",
    "2324": "2023-2024",
    "2223": "2022-2023",
    "2122": "2021-2022",
}


def build_football_data_url(season_code: str, league_code: str) -> str:
    return f"{FOOTBALL_DATA_BASE_URL}/{season_code}/{league_code}.csv"


def download_football_data_leagues(
    season_code: str = "2526",
    leagues: list[str] | None = None,
    fallback_season_code: str = "2425",
    output_dir: str | Path = "data/raw/football-data",
) -> pd.DataFrame:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for league_code in leagues or list(LEAGUE_NAMES):
        attempts = [(season_code, build_football_data_url(season_code, league_code))]
        if fallback_season_code and fallback_season_code != season_code:
            attempts.append((fallback_season_code, build_football_data_url(fallback_season_code, league_code)))
        status = "failed"
        used_url = ""
        saved_path = ""
        error = ""
        for candidate_season, url in attempts:
            try:
                with urlopen(url, timeout=20) as response:
                    payload = response.read()
                header = payload[:500].decode("utf-8", errors="ignore")
                if not {"Date", "HomeTeam", "AwayTeam"}.issubset(set(header.replace("\r", "").split("\n")[0].split(","))):
                    raise ValueError("Downloaded file does not look like a Football-Data match CSV.")
                target = output / f"{league_code}_{candidate_season}.csv"
                target.write_bytes(payload)
                status = "downloaded"
                used_url = url
                saved_path = str(target)
                error = ""
                break
            except (OSError, URLError, ValueError) as exc:
                error = str(exc)
        rows.append({
            "league_code": league_code,
            "league_name": LEAGUE_NAMES.get(league_code, league_code),
            "status": status,
            "downloaded_url": used_url,
            "saved_path": saved_path,
            "error": error,
        })
    return pd.DataFrame(rows)


def download_football_data_seasons(
    season_codes: list[str] | None = None,
    leagues: list[str] | None = None,
    output_dir: str | Path = "data/raw/football-data",
) -> pd.DataFrame:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for season_code in season_codes or list(SEASON_LABELS):
        for league_code in leagues or list(LEAGUE_NAMES):
            url = build_football_data_url(season_code, league_code)
            status = "failed"
            saved_path = ""
            error = ""
            try:
                with urlopen(url, timeout=20) as response:
                    payload = response.read()
                header = payload[:500].decode("utf-8", errors="ignore")
                if not {"Date", "HomeTeam", "AwayTeam"}.issubset(set(header.replace("\r", "").split("\n")[0].split(","))):
                    raise ValueError("Downloaded file does not look like a Football-Data match CSV.")
                target = output / f"{league_code}_{season_code}.csv"
                target.write_bytes(payload)
                status = "downloaded"
                saved_path = str(target)
            except (OSError, URLError, ValueError) as exc:
                error = str(exc)
            rows.append({
                "league_code": league_code,
                "league_name": LEAGUE_NAMES.get(league_code, league_code),
                "season_code": season_code,
                "season_label": SEASON_LABELS.get(season_code, season_code),
                "status": status,
                "downloaded_url": url if status == "downloaded" else "",
                "saved_path": saved_path,
                "error": error,
            })
    return pd.DataFrame(rows)


def _season_from_filename(path: Path, default: str) -> str:
    stem = path.stem
    parts = stem.split("_")
    if len(parts) >= 2 and len(parts[-1]) == 4 and parts[-1].isdigit():
        return f"20{parts[-1][:2]}-20{parts[-1][2:]}"
    return default


def _season_code_from_filename(path: Path) -> str:
    stem = path.stem
    parts = stem.split("_")
    if len(parts) >= 2 and len(parts[-1]) == 4 and parts[-1].isdigit():
        return parts[-1]
    return ""


def _league_from_filename(path: Path) -> str:
    return path.stem.split("_")[0]


def normalize_multi_league_football_data(
    input_path: str | Path,
    output_path: str | Path | None = None,
    season: str = "",
) -> pd.DataFrame:
    root = Path(input_path)
    files = sorted(root.glob("*.csv")) if root.is_dir() else [root]
    frames = []
    for path in files:
        league_code = _league_from_filename(path)
        raw = pd.read_csv(path)
        if not {"Date", "HomeTeam", "AwayTeam"}.issubset(raw.columns):
            continue
        normalized = normalize_current_football_data(
            raw,
            league=league_code,
            season=_season_from_filename(path, season),
            data_source=str(path),
        )
        normalized.insert(3, "league_name", LEAGUE_NAMES.get(league_code, league_code))
        season_code = _season_code_from_filename(path)
        normalized["downloaded_url"] = build_football_data_url(season_code, league_code) if season_code else ""
        frames.append(normalized)
    columns = CURRENT_RESULT_COLUMNS.copy()
    columns.insert(3, "league_name")
    columns.append("downloaded_url")
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    result = result[columns]
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
    return result


def normalize_multi_season_football_data(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    root = Path(input_path)
    files = sorted(root.glob("*.csv")) if root.is_dir() else [root]
    frames = []
    for path in files:
        league_code = _league_from_filename(path)
        season_code = _season_code_from_filename(path)
        if not season_code:
            continue
        raw = pd.read_csv(path)
        if not {"Date", "HomeTeam", "AwayTeam"}.issubset(raw.columns):
            continue
        normalized = normalize_current_football_data(
            raw,
            league=league_code,
            season=SEASON_LABELS.get(season_code, _season_from_filename(path, "")),
            data_source=str(path),
        )
        normalized.insert(3, "league_name", LEAGUE_NAMES.get(league_code, league_code))
        normalized.insert(4, "season_code", season_code)
        normalized.insert(5, "season_label", SEASON_LABELS.get(season_code, normalized["season"].iloc[0] if len(normalized) else season_code))
        normalized["downloaded_url"] = build_football_data_url(season_code, league_code)
        frames.append(normalized)
    columns = CURRENT_RESULT_COLUMNS.copy()
    columns.insert(3, "league_name")
    columns.insert(4, "season_code")
    columns.insert(5, "season_label")
    columns.append("downloaded_url")
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    result = result[columns]
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
    return result
