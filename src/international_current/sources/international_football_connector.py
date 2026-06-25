from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.international_current.sources.eloratings_connector import _finalize_fetch, parse_eloratings_rows
from src.international_current.sources.source_fetching import FetchResult, fetch_public_source, read_local_source, write_fetch_metadata


INTERNATIONAL_FOOTBALL_URLS = [
    "https://www.international-football.net/elo-ratings-table?year=2026&month=06&day=25",
    "https://www.international-football.net/elo-ratings-table",
]


def parse_international_football_ratings(text: str, *, source_url: str = "") -> pd.DataFrame:
    frame = parse_eloratings_rows(text, source_name="international_football_elo", source_url=source_url)
    if not frame.empty:
        frame["rating_source"] = "international_football_elo"
        frame["confidence"] = "medium"
    return frame


def seed_international_football_ratings(cache_dir: str | Path, allow_network: bool = False, local_paths: list[str | Path] | None = None, max_sources: int | None = None) -> tuple[pd.DataFrame, list[FetchResult]]:
    frames: list[pd.DataFrame] = []
    fetches: list[FetchResult] = []
    sources: list[tuple[str | Path, bool]] = [(path, False) for path in (local_paths or [])] + [(url, True) for url in INTERNATIONAL_FOOTBALL_URLS]
    if max_sources is not None:
        sources = sources[:max_sources]
    for locator, is_url in sources:
        fetch, text = fetch_public_source(source_name="international_football_elo", source_url=str(locator), raw_dir=Path(cache_dir) / "raw", allow_network=allow_network) if is_url else read_local_source("international_football_elo", locator)
        try:
            frame = parse_international_football_ratings(text, source_url=str(locator)) if text else pd.DataFrame()
            _finalize_fetch(fetch, text, frame)
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:
            frame = pd.DataFrame()
            _finalize_fetch(fetch, text, frame, str(exc))
        fetches.append(fetch)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), fetches
