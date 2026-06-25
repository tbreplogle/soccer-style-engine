from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.international_current.sources.html_tables import parse_html_tables
from src.international_current.sources.source_fetching import FetchResult, fetch_public_source, read_local_source, write_fetch_metadata
from src.international_current.team_name_normalization import normalize_team_pair, normalize_team_name


FBREF_SCHEDULE_URLS = [
    "https://fbref.com/en/comps/1/schedule/World-Cup-Scores-and-Fixtures",
]

FBREF_TEAM_STATS_URLS = [
    "https://fbref.com/en/comps/1/stats/World-Cup-Stats",
    "https://fbref.com/en/comps/1/shooting/World-Cup-Stats",
]


def _tables(text: str) -> list[pd.DataFrame]:
    return parse_html_tables(text)


def _col(frame: pd.DataFrame, *names: str) -> str | None:
    lowered = {str(col).strip().lower(): str(col) for col in frame.columns}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def parse_fbref_fixture_rows(text: str, *, source_url: str = "") -> pd.DataFrame:
    rows = []
    for table in _tables(text):
        home_col = _col(table, "home", "home_team", "squad")
        away_col = _col(table, "away", "away_team", "opponent")
        date_col = _col(table, "date", "match_date")
        if not home_col or not away_col:
            continue
        for _, item in table.iterrows():
            home, away, warnings = normalize_team_pair(str(item.get(home_col, "")), str(item.get(away_col, "")))
            if not home or not away or home.lower() == "nan" or away.lower() == "nan":
                continue
            rows.append({
                "match_date": "" if not date_col else str(item.get(date_col, "")),
                "kickoff_time": str(item.get(_col(table, "time") or "", "")),
                "competition": "FIFA World Cup",
                "round_name": str(item.get(_col(table, "round", "wk") or "", "")),
                "group_name": "",
                "home_team": home,
                "away_team": away,
                "neutral_site": "unknown",
                "venue": str(item.get(_col(table, "venue") or "", "")),
                "source_name": "fbref_schedule",
                "source_url": source_url,
                "source_tier": "real",
                "source_status": "scheduled",
                "is_sample_data": False,
                "reliability_status": "fetched_public_source",
                "fixture_confidence": "medium",
                "warnings": " | ".join(warnings + ["FBref schedule table is not event/tracking style data."]),
            })
    return pd.DataFrame(rows)


def _num(value: object) -> float | None:
    try:
        text = str(value).replace("%", "").strip()
        return None if not text or text.lower() == "nan" else float(text)
    except ValueError:
        return None


def parse_fbref_stat_rows(text: str, *, source_url: str = "") -> pd.DataFrame:
    rows = []
    for table in _tables(text):
        team_col = _col(table, "squad", "team", "team_name")
        if not team_col:
            continue
        for _, item in table.iterrows():
            raw = str(item.get(team_col, ""))
            if not raw or raw.lower() == "nan":
                continue
            normalized = normalize_team_name(raw)
            rows.append({
                "team_name": raw,
                "normalized_team_name": normalized.normalized_name,
                "goals_for_per_match": _num(item.get(_col(table, "gf", "gls") or "")),
                "goals_against_per_match": _num(item.get(_col(table, "ga") or "")),
                "xg_for_per_match": _num(item.get(_col(table, "xg") or "")),
                "xg_against_per_match": _num(item.get(_col(table, "xga") or "")),
                "shots_for_per_match": _num(item.get(_col(table, "sh") or "")),
                "shots_against_per_match": None,
                "shots_on_target_for_per_match": _num(item.get(_col(table, "sot") or "")),
                "shots_on_target_against_per_match": None,
                "clean_sheet_rate": None,
                "failed_to_score_rate": None,
                "cards_per_match": _num(item.get(_col(table, "crdy") or "")),
                "red_cards_per_match": _num(item.get(_col(table, "crdr") or "")),
                "source_name": "fbref_team_stats",
                "source_status": "fetched_public_source",
                "warning": "FBref public table parsed; blank fields were not present in source.",
            })
    return pd.DataFrame(rows)


def seed_fbref_fixtures(cache_dir: str | Path, allow_network: bool = False, local_paths: list[str | Path] | None = None, max_sources: int | None = None) -> tuple[pd.DataFrame, list[FetchResult]]:
    return _seed_fbref(parse_fbref_fixture_rows, "fbref_schedule", FBREF_SCHEDULE_URLS, cache_dir, allow_network, local_paths, max_sources)


def seed_fbref_stats(cache_dir: str | Path, allow_network: bool = False, local_paths: list[str | Path] | None = None, max_sources: int | None = None) -> tuple[pd.DataFrame, list[FetchResult]]:
    return _seed_fbref(parse_fbref_stat_rows, "fbref_team_stats", FBREF_TEAM_STATS_URLS, cache_dir, allow_network, local_paths, max_sources)


def _seed_fbref(parser, source_name: str, urls: list[str], cache_dir: str | Path, allow_network: bool, local_paths: list[str | Path] | None, max_sources: int | None) -> tuple[pd.DataFrame, list[FetchResult]]:
    frames: list[pd.DataFrame] = []
    fetches: list[FetchResult] = []
    sources: list[tuple[str | Path, bool]] = [(path, False) for path in (local_paths or [])] + [(url, True) for url in urls]
    if max_sources is not None:
        sources = sources[:max_sources]
    for locator, is_url in sources:
        fetch, text = fetch_public_source(source_name=source_name, source_url=str(locator), raw_dir=Path(cache_dir) / "raw", allow_network=allow_network) if is_url else read_local_source(source_name, locator)
        try:
            frame = parser(text, source_url=str(locator)) if text else pd.DataFrame()
            fetch.status = "success" if len(frame) else fetch.status if fetch.status in {"blocked", "not_found", "cache_miss"} else "empty"
            write_fetch_metadata(fetch, len(frame))
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:
            fetch.status = "parse_error"
            fetch.error_message = str(exc)
            write_fetch_metadata(fetch, 0)
        fetches.append(fetch)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), fetches
