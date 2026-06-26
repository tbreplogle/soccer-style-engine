from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.international_current.fixture_deduplication import deduplicate_fixtures, write_fixture_deduplication_outputs
from src.international_current.sources.eloratings_connector import seed_eloratings
from src.international_current.sources.espn_connector import seed_espn_fixtures
from src.international_current.sources.fbref_connector import seed_fbref_fixtures, seed_fbref_stats
from src.international_current.sources.international_football_connector import seed_international_football_ratings
from src.international_current.sources.openfootball_connector import seed_openfootball_fixtures
from src.international_current.sources.source_cache import mirror_root_cache, write_parsed_cache
from src.international_current.sources.source_fetching import FetchResult


def _empty_fixture_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "match_date", "kickoff_time", "competition", "round_name", "group_name", "home_team", "away_team",
        "neutral_site", "venue", "source_name", "source_url", "source_tier", "source_status", "is_sample_data",
        "reliability_status", "fixture_confidence", "warnings",
    ])


def _empty_rating_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "team_name", "normalized_team_name", "rating", "rating_source", "rating_source_url", "rating_date",
        "source_status", "confidence", "warning",
    ])


def _empty_stat_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "team_name", "normalized_team_name", "goals_for_per_match", "goals_against_per_match",
        "xg_for_per_match", "xg_against_per_match", "shots_for_per_match", "shots_against_per_match",
        "shots_on_target_for_per_match", "shots_on_target_against_per_match", "clean_sheet_rate",
        "failed_to_score_rate", "cards_per_match", "red_cards_per_match", "source_name", "source_status", "warning",
    ])


def _concat(frames: list[pd.DataFrame], fallback: pd.DataFrame) -> pd.DataFrame:
    present = [frame for frame in frames if frame is not None and not frame.empty]
    if not present:
        return fallback.copy()
    return pd.concat(present, ignore_index=True).drop_duplicates()


def _seed_results(fetches: list[FetchResult], source_type: str) -> pd.DataFrame:
    rows = []
    for fetch in fetches:
        row = fetch.to_dict()
        row["source_type"] = source_type
        rows.append(row)
    return pd.DataFrame(rows)


def _rating_diagnostics(fetches: list[FetchResult]) -> pd.DataFrame:
    rows = []
    for fetch in fetches:
        if not fetch.diagnostic_path:
            continue
        path = Path(fetch.diagnostic_path)
        if not path.exists():
            continue
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            rows.append({
                "source_name": fetch.source_name,
                "source_url": fetch.source_url,
                "parse_status": "parse_error",
                "parse_error": f"Could not read diagnostic JSON: {path}",
            })
    return pd.DataFrame(rows)


def _summary_lines(
    *,
    as_of_date: str,
    allow_network: bool,
    fixture_rows: int,
    rating_rows: int,
    stat_rows: int,
    strict: bool,
    fetch_results: pd.DataFrame,
) -> list[str]:
    status_counts = fetch_results["status"].value_counts().to_dict() if not fetch_results.empty else {}
    strict_status = "pass" if not strict or (fixture_rows > 0 and rating_rows > 0) else "fail"
    return [
        "# Current International Cache Seed",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"As of date: {as_of_date}",
        f"Network allowed: `{allow_network}`",
        f"Strict status: `{strict_status}`",
        "",
        "## Rows Parsed",
        "",
        f"- Fixture rows: {fixture_rows}",
        f"- Rating rows: {rating_rows}",
        f"- Stat rows: {stat_rows}",
        f"- Source status counts: {status_counts}",
        "",
        "## Guardrails",
        "",
        "- Current StatsBomb is not used.",
        "- Missing xG/shots fields remain blank.",
        "- No Selenium, login, CAPTCHA, anti-bot, or paywall bypass is used.",
        "- Proxy score adjustments remain disabled.",
        "- Output is projection review context, not betting guidance.",
    ]


def seed_current_international_cache(
    *,
    as_of_date: str,
    competition: str = "FIFA World Cup",
    allow_network: bool = False,
    seed_fixtures: bool = False,
    seed_ratings: bool = False,
    seed_stats: bool = False,
    seed_all: bool = False,
    force_refresh: bool = False,
    cache_dir: str | Path = "data/source_cache/current_international",
    output_dir: str | Path = "outputs/current_international",
    max_sources: int | None = None,
    max_matches: int | None = None,
    strict: bool = False,
    local_fixture_paths: dict[str, list[str | Path]] | None = None,
    local_rating_paths: dict[str, list[str | Path]] | None = None,
    local_stat_paths: dict[str, list[str | Path]] | None = None,
    dedupe_fixtures: bool = True,
    dedupe_review_threshold: float = 0.75,
    source_priority_mode: str = "balanced",
) -> dict[str, Any]:
    if seed_all or not any([seed_fixtures, seed_ratings, seed_stats]):
        seed_fixtures = seed_ratings = seed_stats = True
    cache = Path(cache_dir)
    run_dir = Path(output_dir) / as_of_date / "cache_seed"
    run_dir.mkdir(parents=True, exist_ok=True)
    fixture_frames: list[pd.DataFrame] = []
    rating_frames: list[pd.DataFrame] = []
    stat_frames: list[pd.DataFrame] = []
    fixture_fetches: list[FetchResult] = []
    rating_fetches: list[FetchResult] = []
    stat_fetches: list[FetchResult] = []
    local_fixture_paths = local_fixture_paths or {}
    local_rating_paths = local_rating_paths or {}
    local_stat_paths = local_stat_paths or {}

    if seed_fixtures:
        for frame, fetches in [
            seed_openfootball_fixtures(cache_dir=cache, allow_network=allow_network, local_paths=local_fixture_paths.get("openfootball_worldcup"), max_sources=max_sources),
            seed_espn_fixtures(cache_dir=cache, allow_network=allow_network, local_paths=local_fixture_paths.get("espn_scoreboard"), max_sources=max_sources),
            seed_fbref_fixtures(cache_dir=cache, allow_network=allow_network, local_paths=local_fixture_paths.get("fbref_schedule"), max_sources=max_sources),
        ]:
            fixture_frames.append(frame)
            fixture_fetches.extend(fetches)
    if seed_ratings:
        for frame, fetches in [
            seed_eloratings(cache_dir=cache, allow_network=allow_network, local_paths=local_rating_paths.get("eloratings"), max_sources=max_sources),
            seed_international_football_ratings(cache_dir=cache, allow_network=allow_network, local_paths=local_rating_paths.get("international_football_elo"), max_sources=max_sources),
        ]:
            rating_frames.append(frame)
            rating_fetches.extend(fetches)
    if seed_stats:
        frame, fetches = seed_fbref_stats(cache_dir=cache, allow_network=allow_network, local_paths=local_stat_paths.get("fbref_team_stats"), max_sources=max_sources)
        stat_frames.append(frame)
        stat_fetches.extend(fetches)

    fixtures = _concat(fixture_frames, _empty_fixture_frame())
    if max_matches is not None and not fixtures.empty:
        fixtures = fixtures.head(max_matches)
    dedupe_result = deduplicate_fixtures(
        fixtures,
        enabled=dedupe_fixtures,
        review_threshold=dedupe_review_threshold,
        source_priority_mode=source_priority_mode,
    )
    dedupe_paths = write_fixture_deduplication_outputs(run_dir=Path(output_dir) / as_of_date, dedupe_result=dedupe_result)
    ratings = _concat(rating_frames, _empty_rating_frame())
    stats = _concat(stat_frames, _empty_stat_frame())
    fetch_results = pd.concat([
        _seed_results(fixture_fetches, "fixture"),
        _seed_results(rating_fetches, "rating"),
        _seed_results(stat_fetches, "stat"),
    ], ignore_index=True) if (fixture_fetches or rating_fetches or stat_fetches) else pd.DataFrame()

    fixture_cache_path = write_parsed_cache(fixtures, cache, "fixtures", {"competition": competition, "force_refresh": force_refresh})
    rating_cache_path = write_parsed_cache(ratings, cache, "ratings", {"competition": competition, "force_refresh": force_refresh})
    stat_cache_path = write_parsed_cache(stats, cache, "stats", {"competition": competition, "force_refresh": force_refresh})
    mirror_root_cache(fixtures, cache, "fixtures")
    mirror_root_cache(ratings, cache, "ratings")
    mirror_root_cache(stats, cache, "stats")

    paths = {
        "cache_seed_summary": run_dir / "cache_seed_summary.md",
        "fixture_seed_results": run_dir / "fixture_seed_results.csv",
        "rating_seed_results": run_dir / "rating_seed_results.csv",
        "stat_seed_results": run_dir / "stat_seed_results.csv",
        "source_fetch_results": run_dir / "source_fetch_results.csv",
        "rating_parse_diagnostics": run_dir / "rating_parse_diagnostics.csv",
        "parsed_fixture_rows": run_dir / "parsed_fixture_rows.csv",
        "parsed_rating_rows": run_dir / "parsed_rating_rows.csv",
        "parsed_stat_rows": run_dir / "parsed_stat_rows.csv",
    }
    _seed_results(fixture_fetches, "fixture").to_csv(paths["fixture_seed_results"], index=False)
    _seed_results(rating_fetches, "rating").to_csv(paths["rating_seed_results"], index=False)
    _seed_results(stat_fetches, "stat").to_csv(paths["stat_seed_results"], index=False)
    fetch_results.to_csv(paths["source_fetch_results"], index=False)
    _rating_diagnostics(rating_fetches).to_csv(paths["rating_parse_diagnostics"], index=False)
    fixtures.to_csv(paths["parsed_fixture_rows"], index=False)
    ratings.to_csv(paths["parsed_rating_rows"], index=False)
    stats.to_csv(paths["parsed_stat_rows"], index=False)
    paths["cache_seed_summary"].write_text("\n".join(_summary_lines(
        as_of_date=as_of_date,
        allow_network=allow_network,
        fixture_rows=len(fixtures),
        rating_rows=len(ratings),
        stat_rows=len(stats),
        strict=strict,
        fetch_results=fetch_results,
    )), encoding="utf-8")
    return {
        "run_dir": run_dir,
        "paths": {**{key: str(value) for key, value in paths.items()}, **dedupe_paths},
        "cache_paths": {
            "fixtures": str(fixture_cache_path),
            "ratings": str(rating_cache_path),
            "stats": str(stat_cache_path),
        },
        "fixtures": fixtures,
        "ratings": ratings,
        "stats": stats,
        "fetch_results": fetch_results,
        "fixture_deduplication": dedupe_result,
        "strict_status": "pass" if not strict or (len(fixtures) > 0 and len(ratings) > 0) else "fail",
    }
