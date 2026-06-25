from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pandas as pd

from src.international_current.sources.html_tables import parse_html_tables
from src.international_current.sources.source_fetching import FetchResult, fetch_public_source, read_local_source, write_fetch_metadata
from src.international_current.team_name_normalization import normalize_team_name


ELORATINGS_URLS = [
    "https://www.eloratings.net/World.tsv",
    "https://www.eloratings.net/",
]

ELORATINGS_TEAM_DICTIONARY_URL = "https://www.eloratings.net/en.teams.tsv"

EXPECTED_COMMON_TEAMS = [
    "Spain",
    "Argentina",
    "France",
    "England",
    "Brazil",
    "Germany",
    "Netherlands",
    "Mexico",
    "United States",
    "Japan",
]

LOW_COVERAGE_STATUS = "parse_error_or_low_coverage"
RATING_WARNING = "Rating is a strength prior only, not style data."
MIN_GLOBAL_RATING_ROWS = 40

_TEAM_SKIP_WORDS = {
    "rating", "ratings", "rank", "ranking", "team", "country", "nation", "date", "elo", "world",
    "football", "soccer", "previous", "next", "year", "month", "day", "login", "register", "home",
}


def _num(value: object) -> float | None:
    try:
        text = str(value).replace(",", "").replace("\u2212", "-").strip()
        return None if not text or text.lower() == "nan" else float(text)
    except ValueError:
        return None


def _plausible_rating(value: object) -> float | None:
    rating = _num(value)
    if rating is None or rating < 500 or rating > 2500:
        return None
    return rating


def _clean_team_name(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = unquote(text)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#039;", "'")
    text = text.replace("\u00a0", " ").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^\d+\s*[.)-]?\s*", "", text)
    return text.strip(" .:-")


def _rating_row(
    *,
    raw: str,
    rating: float,
    source_name: str,
    source_url: str,
    confidence: str,
    rating_date: str = "",
    extra_warning: str = "",
) -> dict[str, Any] | None:
    team = _clean_team_name(raw)
    if not team or team.lower() in _TEAM_SKIP_WORDS or len(team) > 60:
        return None
    normalized = normalize_team_name(team)
    if not normalized.normalized_name:
        return None
    warnings = [normalized.warning, RATING_WARNING, extra_warning]
    return {
        "team_name": team,
        "normalized_team_name": normalized.normalized_name,
        "rating": rating,
        "rating_source": source_name,
        "rating_source_url": source_url,
        "rating_date": rating_date,
        "source_status": "fetched_public_source",
        "confidence": confidence,
        "warning": " | ".join(w for w in warnings if w),
    }


def _dedupe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    priority = {"high": 3, "medium": 2, "low": 1}
    frame = pd.DataFrame(rows)
    frame["_priority"] = frame["confidence"].map(priority).fillna(0)
    frame = frame.sort_values(["normalized_team_name", "_priority", "rating"], ascending=[True, False, False])
    return frame.drop_duplicates("normalized_team_name").drop(columns=["_priority"]).reset_index(drop=True)


def parse_eloratings_team_dictionary(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw_line in text.splitlines():
        parts = [part.strip() for part in raw_line.split("\t") if part.strip()]
        if len(parts) >= 2 and re.fullmatch(r"[A-Z0-9]{2,8}(?:_loc)?", parts[0]):
            if not parts[0].endswith("_loc"):
                mapping[parts[0]] = _clean_team_name(parts[1])
    return mapping


def _parse_csv(text: str, source_name: str, source_url: str) -> pd.DataFrame:
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        raw = row.get("team_name") or row.get("team") or row.get("Team") or row.get("country") or ""
        rating = _plausible_rating(row.get("rating") or row.get("rating_value") or row.get("elo") or row.get("Elo"))
        if not raw or rating is None:
            continue
        parsed = _rating_row(
            raw=raw,
            rating=rating,
            source_name=source_name,
            source_url=row.get("source_url") or source_url,
            rating_date=row.get("rating_date") or row.get("date") or "",
            confidence="high",
        )
        if parsed:
            rows.append(parsed)
    return _dedupe(rows)


def _parse_eloratings_tsv(text: str, source_name: str, source_url: str, team_dictionary: dict[str, str] | None = None) -> pd.DataFrame:
    rows = []
    team_dictionary = team_dictionary or {}
    for raw_line in text.splitlines():
        parts = [part.strip() for part in raw_line.split("\t")]
        if len(parts) < 4:
            continue
        rating = _plausible_rating(parts[3])
        code = parts[2].strip()
        raw = team_dictionary.get(code, code)
        if rating is None or not raw or raw == code:
            continue
        parsed = _rating_row(
            raw=raw,
            rating=rating,
            source_name=source_name,
            source_url=source_url,
            confidence="high",
            extra_warning="Parsed from public EloRatings World.tsv current rating table.",
        )
        if parsed:
            rows.append(parsed)
    return _dedupe(rows)


def _parse_html(text: str, source_name: str, source_url: str) -> pd.DataFrame:
    rows = []
    for table in parse_html_tables(text):
        columns = {str(col).strip().lower(): col for col in table.columns}
        team_col = columns.get("team") or columns.get("country") or columns.get("nation")
        rating_col = columns.get("rating") or columns.get("elo") or columns.get("elorating")
        if team_col is None or rating_col is None:
            continue
        date_col = columns.get("date") or columns.get("rating_date")
        for _, item in table.iterrows():
            raw = str(item.get(team_col, ""))
            rating = _plausible_rating(item.get(rating_col))
            if not raw or rating is None:
                continue
            parsed = _rating_row(
                raw=raw,
                rating=rating,
                source_name=source_name,
                source_url=source_url,
                rating_date=str(item.get(date_col, "")) if date_col is not None else "",
                confidence="medium",
            )
            if parsed:
                rows.append(parsed)
    rows.extend(_parse_html_rank_rows(text, source_name, source_url))
    return _dedupe(rows)


def _parse_html_rank_rows(text: str, source_name: str, source_url: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    row_pattern = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    cell_pattern = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
    for match in row_pattern.finditer(text):
        cells = [_clean_team_name(cell) for cell in cell_pattern.findall(match.group(1))]
        cells = [cell for cell in cells if cell]
        if len(cells) < 2:
            continue
        rating_candidates = [(idx, _plausible_rating(cell)) for idx, cell in enumerate(cells)]
        rating_candidates = [(idx, rating) for idx, rating in rating_candidates if rating is not None]
        if not rating_candidates:
            continue
        rating_idx, rating = rating_candidates[-1]
        team_candidates = [cell for idx, cell in enumerate(cells[:rating_idx]) if _plausible_rating(cell) is None]
        if not team_candidates:
            continue
        parsed = _rating_row(
            raw=team_candidates[-1],
            rating=float(rating),
            source_name=source_name,
            source_url=source_url,
            confidence="medium",
        )
        if parsed:
            rows.append(parsed)
    return rows


def _parse_text_rows(text: str, source_name: str, source_url: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    stripped = re.sub(r"<script\b.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<style\b.*?</style>", " ", stripped, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<[^>]+>", "\n", stripped)
    stripped = stripped.replace("&nbsp;", " ").replace("&amp;", "&")
    line_pattern = re.compile(
        r"(?:^|\n)\s*(?:\d{1,3}\s*[.)-]?\s+)?"
        r"(?P<team>[A-Z][A-Za-zÀ-ÿ' .&/-]{2,55}?)"
        r"\s+(?P<rating>[5-9]\d{2}|1\d{3}|2[0-4]\d{2}|2500)(?:\s|$)"
    )
    js_pattern = re.compile(
        r"[\"'](?P<team>[A-Z][A-Za-zÀ-ÿ' .&/-]{2,55}?)[\"']\s*[,:\]]\s*"
        r"(?P<rating>[5-9]\d{2}|1\d{3}|2[0-4]\d{2}|2500)"
    )
    for pattern in [line_pattern, js_pattern]:
        for match in pattern.finditer(stripped):
            rating = _plausible_rating(match.group("rating"))
            team = _clean_team_name(match.group("team"))
            if rating is None or any(word in team.lower().split() for word in _TEAM_SKIP_WORDS):
                continue
            parsed = _rating_row(
                raw=team,
                rating=rating,
                source_name=source_name,
                source_url=source_url,
                confidence="low",
                extra_warning="Parsed by conservative text fallback.",
            )
            if parsed:
                rows.append(parsed)
    return _dedupe(rows)


def parse_eloratings_rows(
    text: str,
    *,
    source_name: str = "eloratings",
    source_url: str = "",
    team_dictionary: dict[str, str] | None = None,
) -> pd.DataFrame:
    if not text.strip():
        return pd.DataFrame()
    if "\t" in text and not any(header in text[:200].lower() for header in ["team", "country", "rating", "elo"]):
        frame = _parse_eloratings_tsv(text, source_name, source_url, team_dictionary)
        if not frame.empty:
            return frame
    csv_frame = _parse_csv(text, source_name, source_url)
    if not csv_frame.empty:
        return csv_frame
    if "<table" in text.lower():
        html_frame = _parse_html(text, source_name, source_url)
        if not html_frame.empty:
            return html_frame
    return _parse_text_rows(text, source_name, source_url)


def _detect_rating_like_rows(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"(?:[A-Z][A-Za-zÀ-ÿ' .&/-]{2,55}\s+)(?:[5-9]\d{2}|1\d{3}|2[0-4]\d{2}|2500)", text))


def _snippets(text: str, limit: int = 5) -> list[str]:
    cleaned = re.sub(r"<script\b.*?</script>", " ", text or "", flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style\b.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    lines = [" ".join(line.split()) for line in cleaned.splitlines()]
    useful = [
        line[:220] for line in lines
        if len(line) >= 25 and not any(skip in line.lower() for skip in ["google analytics", "jquery", "stylesheet"])
    ]
    return useful[:limit]


def validate_rating_frame(frame: pd.DataFrame) -> dict[str, Any]:
    teams = set(frame.get("normalized_team_name", pd.Series(dtype=str)).dropna().astype(str)) if not frame.empty else set()
    missing = [team for team in EXPECTED_COMMON_TEAMS if team not in teams]
    status = "success" if len(frame) >= MIN_GLOBAL_RATING_ROWS and len(missing) == 0 else LOW_COVERAGE_STATUS
    return {
        "parse_status": status,
        "row_count": len(frame),
        "expected_common_teams_found": len(EXPECTED_COMMON_TEAMS) - len(missing),
        "expected_common_teams_missing": missing,
    }


def build_rating_diagnostic(fetch: FetchResult, text: str, frame: pd.DataFrame, parse_status: str, parse_error: str = "") -> dict[str, Any]:
    try:
        tables_count = len(parse_html_tables(text)) if text else 0
    except Exception:
        tables_count = 0
    validation = validate_rating_frame(frame)
    return {
        "source_name": fetch.source_name,
        "source_url": fetch.source_url,
        "http_status": fetch.http_status,
        "content_length": len(text or ""),
        "first_useful_text_snippets": " || ".join(_snippets(text)),
        "detected_tables_count": tables_count,
        "detected_country_rating_rows_count": _detect_rating_like_rows(text or ""),
        "parse_status": parse_status,
        "parse_error": parse_error,
        "row_count": len(frame),
        "expected_common_teams_found": validation["expected_common_teams_found"],
        "expected_common_teams_missing": ", ".join(validation["expected_common_teams_missing"]),
    }


def write_rating_diagnostic(fetch: FetchResult, text: str, frame: pd.DataFrame, parse_status: str, parse_error: str = "") -> FetchResult:
    raw = Path(fetch.raw_path) if fetch.raw_path else Path("rating_source")
    diagnostic_path = raw.with_suffix(raw.suffix + ".diagnostic.json")
    diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostic_path.write_text(json.dumps(build_rating_diagnostic(fetch, text, frame, parse_status, parse_error), indent=2), encoding="utf-8")
    fetch.diagnostic_path = str(diagnostic_path)
    return fetch


def _finalize_fetch(fetch: FetchResult, text: str, frame: pd.DataFrame, parse_error: str = "") -> FetchResult:
    if parse_error:
        fetch.status = "parse_error"
        fetch.error_message = parse_error
        parse_status = "parse_error"
    elif fetch.status in {"blocked", "not_found", "cache_miss"}:
        parse_status = fetch.status
    else:
        validation = validate_rating_frame(frame)
        parse_status = validation["parse_status"]
        fetch.status = "success" if parse_status == "success" else LOW_COVERAGE_STATUS
        if parse_status == LOW_COVERAGE_STATUS:
            fetch.error_message = (
                f"Parsed {len(frame)} rating rows; missing expected common teams: "
                f"{', '.join(validation['expected_common_teams_missing']) or 'none'}."
            )
    write_rating_diagnostic(fetch, text, frame, parse_status, parse_error)
    return write_fetch_metadata(fetch, len(frame))


def seed_eloratings(cache_dir: str | Path, allow_network: bool = False, local_paths: list[str | Path] | None = None, max_sources: int | None = None) -> tuple[pd.DataFrame, list[FetchResult]]:
    frames: list[pd.DataFrame] = []
    fetches: list[FetchResult] = []
    sources: list[tuple[str | Path, bool]] = [(path, False) for path in (local_paths or [])] + [(url, True) for url in ELORATINGS_URLS]
    if max_sources is not None:
        sources = sources[:max_sources]
    dictionary: dict[str, str] = {}
    if any(str(locator).endswith(".tsv") for locator, _ in sources):
        dictionary_fetch, dictionary_text = fetch_public_source(
            source_name="eloratings_team_dictionary",
            source_url=ELORATINGS_TEAM_DICTIONARY_URL,
            raw_dir=Path(cache_dir) / "raw",
            allow_network=allow_network,
        )
        dictionary = parse_eloratings_team_dictionary(dictionary_text)
        write_fetch_metadata(dictionary_fetch, len(dictionary))
        fetches.append(dictionary_fetch)
    for locator, is_url in sources:
        fetch, text = fetch_public_source(source_name="eloratings", source_url=str(locator), raw_dir=Path(cache_dir) / "raw", allow_network=allow_network) if is_url else read_local_source("eloratings", locator)
        try:
            frame = parse_eloratings_rows(text, source_url=str(locator), team_dictionary=dictionary) if text else pd.DataFrame()
            _finalize_fetch(fetch, text, frame)
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:
            frame = pd.DataFrame()
            _finalize_fetch(fetch, text, frame, str(exc))
        fetches.append(fetch)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), fetches
