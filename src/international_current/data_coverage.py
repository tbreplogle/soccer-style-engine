from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _has_value(value: object) -> bool:
    return not pd.isna(value) and str(value).strip() != ""


def _support_label(fixture_found: bool, home_rating: bool, away_rating: bool, stats_found: bool, xg_available: bool, source_tier: str) -> str:
    if source_tier == "sample":
        return "sample_demo_only"
    prefix = "manual_fixture" if source_tier == "manual" else "real_fixture"
    if xg_available:
        return f"{prefix}_xg_stats"
    if stats_found:
        return f"{prefix}_basic_stats"
    if home_rating and away_rating:
        return f"{prefix}_full_rating"
    if home_rating or away_rating:
        return f"{prefix}_partial_rating"
    if fixture_found:
        return f"{prefix}_missing_rating"
    return "insufficient"


def build_match_data_coverage(
    fixtures: pd.DataFrame,
    ratings: pd.DataFrame,
    stats: pd.DataFrame,
) -> pd.DataFrame:
    rating_teams = set(ratings.get("normalized_team_name", pd.Series(dtype=str)).dropna().astype(str))
    stat_teams = set(stats.get("normalized_team_name", pd.Series(dtype=str)).dropna().astype(str))
    xg_teams = set(
        stats.loc[
            stats.get("xg_for_per_match", pd.Series(dtype=object)).notna()
            | stats.get("xg_against_per_match", pd.Series(dtype=object)).notna(),
            "normalized_team_name",
        ].dropna().astype(str)
    ) if not stats.empty and "normalized_team_name" in stats.columns else set()
    shot_teams = set(
        stats.loc[
            stats.get("shots_for_per_match", pd.Series(dtype=object)).notna()
            | stats.get("shots_against_per_match", pd.Series(dtype=object)).notna(),
            "normalized_team_name",
        ].dropna().astype(str)
    ) if not stats.empty and "normalized_team_name" in stats.columns else set()
    rows = []
    for _, fixture in fixtures.iterrows():
        home = str(fixture.get("home_team", ""))
        away = str(fixture.get("away_team", ""))
        source_tier = str(fixture.get("source_tier", "real"))
        home_rating = home in rating_teams
        away_rating = away in rating_teams
        home_stats = home in stat_teams
        away_stats = away in stat_teams
        xg_available = home in xg_teams and away in xg_teams
        shots_available = home in shot_teams and away in shot_teams
        missing = []
        if not home_rating:
            missing.append(f"home_rating:{home}")
        if not away_rating:
            missing.append(f"away_rating:{away}")
        if not home_stats:
            missing.append(f"home_current_stats:{home}")
        if not away_stats:
            missing.append(f"away_current_stats:{away}")
        if not xg_available:
            missing.append("xg")
        if not shots_available:
            missing.append("shots")
        rows.append({
            "match_date": fixture.get("match_date", ""),
            "home_team": home,
            "away_team": away,
            "fixture_found": True,
            "home_rating_found": home_rating,
            "away_rating_found": away_rating,
            "home_current_stats_found": home_stats,
            "away_current_stats_found": away_stats,
            "xg_available": xg_available,
            "shots_available": shots_available,
            "lineup_available": False,
            "injury_available": False,
            "style_inputs_available": False,
            "data_support_level": _support_label(True, home_rating, away_rating, home_stats and away_stats, xg_available, source_tier),
            "missing_items": "; ".join(missing),
            "recommended_next_source": "rating cache" if not (home_rating and away_rating) else "basic stat/xG source" if not xg_available else "style-aware validation",
        })
    return pd.DataFrame(rows)


def _coverage_frame(frame: pd.DataFrame, kind: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame([{"coverage_type": kind, "rows": 0, "status": "missing"}])
    return pd.DataFrame([{"coverage_type": kind, "rows": len(frame), "status": "available"}])


def write_coverage_report(
    *,
    output_dir: str | Path,
    source_audit: pd.DataFrame,
    fixtures: pd.DataFrame,
    ratings: pd.DataFrame,
    stats: pd.DataFrame,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    match_coverage = build_match_data_coverage(fixtures, ratings, stats)
    fixture_coverage = _coverage_frame(fixtures, "fixture")
    rating_coverage = _coverage_frame(ratings, "rating")
    stat_coverage = _coverage_frame(stats, "stat")
    paths = {
        "source_audit": output / "source_audit.csv",
        "fixture_coverage": output / "fixture_coverage.csv",
        "rating_coverage": output / "rating_coverage.csv",
        "stat_coverage": output / "stat_coverage.csv",
        "match_data_coverage": output / "match_data_coverage.csv",
        "source_audit_summary": output / "source_audit_summary.md",
    }
    source_audit.to_csv(paths["source_audit"], index=False)
    fixture_coverage.to_csv(paths["fixture_coverage"], index=False)
    rating_coverage.to_csv(paths["rating_coverage"], index=False)
    stat_coverage.to_csv(paths["stat_coverage"], index=False)
    match_coverage.to_csv(paths["match_data_coverage"], index=False)
    real_fixtures = int((fixtures.get("source_tier", pd.Series(dtype=str)) == "real").sum()) if not fixtures.empty else 0
    manual_fixtures = int((fixtures.get("source_tier", pd.Series(dtype=str)) == "manual").sum()) if not fixtures.empty else 0
    sample_fixtures = int((fixtures.get("source_tier", pd.Series(dtype=str)) == "sample").sum()) if not fixtures.empty else 0
    missing_ratings = sorted(set(
        item.split(":", 1)[1]
        for text in match_coverage.get("missing_items", pd.Series(dtype=str)).astype(str)
        for item in text.split("; ")
        if item.startswith(("home_rating:", "away_rating:"))
    ))
    lines = [
        "# Current International Source Audit",
        "",
        f"Fixture rows: {len(fixtures)}",
        f"Real fixture rows: {real_fixtures}",
        f"Manual fixture rows: {manual_fixtures}",
        f"Sample fixture rows: {sample_fixtures}",
        f"Rating rows: {len(ratings)}",
        f"Stat rows: {len(stats)}",
        f"Teams still missing ratings: {', '.join(missing_ratings) if missing_ratings else 'None'}",
        "",
        "## Guardrails",
        "",
        "- Current StatsBomb is not used.",
        "- Missing xG/shots fields remain blank.",
        "- Proxy score adjustments remain disabled.",
        "- Output is projection review context, not betting guidance.",
    ]
    paths["source_audit_summary"].write_text("\n".join(lines), encoding="utf-8")
    return {"paths": {key: str(value) for key, value in paths.items()}, "match_coverage": match_coverage}
