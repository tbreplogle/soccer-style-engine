from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.reports.projection_report import CLUB_PROFILES, INTERNATIONAL_PROFILES, _club_row, _intl_row
from src.reports.report_formatting import split_csv_arg, write_csv, write_markdown_report


CLUB_SLATE_COLUMNS = [
    "slate_date",
    "slate_type",
    "league",
    "home_team",
    "away_team",
    "projection_profile",
    "baseline_mode_used",
    "market_influence_level",
    "home_xg_final",
    "away_xg_final",
    "projected_total",
    "most_likely_score",
    "home_win_prob",
    "draw_prob",
    "away_win_prob",
    "over_2_5_prob",
    "under_2_5_prob",
    "btts_prob",
    "confidence_score",
    "confidence_label",
    "confidence_reasons",
    "risk_flags",
    "data_quality_flags",
    "market_gap_summary",
    "model_market_gap_summary",
    "proxy_style_explanation",
    "warnings",
    "data_mode",
    "betting_recommendation",
]

INTERNATIONAL_SLATE_COLUMNS = [
    "slate_date",
    "slate_type",
    "team_a",
    "team_b",
    "neutral_site",
    "competition_context",
    "projection_profile",
    "baseline_mode_used",
    "team_a_xg_final",
    "team_b_xg_final",
    "projected_total",
    "most_likely_score",
    "team_a_win_prob",
    "draw_prob",
    "team_b_win_prob",
    "over_2_5_prob",
    "under_2_5_prob",
    "btts_prob",
    "confidence_score",
    "confidence_label",
    "confidence_reasons",
    "risk_flags",
    "data_quality_flags",
    "international_context_warnings",
    "data_mode",
    "betting_recommendation",
]


def _load_frame(path: str | Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    return data


def _manual_club_matchups(path: str | Path, default_date: str, default_league: str | None) -> list[dict[str, Any]]:
    rows = pd.read_csv(path).to_dict("records")
    return [
        {
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "league": row.get("league") or default_league,
            "as_of_date": row.get("as_of_date") or default_date,
        }
        for row in rows
    ]


def _club_candidates(data: pd.DataFrame, as_of_date: str, league: str | None, slate_type: str, max_matches: int, matchups_csv: str | Path | None) -> tuple[str, list[dict[str, Any]]]:
    frame = data[data["league"].eq(league)].copy() if league and "league" in data.columns else data.copy()
    if matchups_csv:
        return "manual_matchup_slate", _manual_club_matchups(matchups_csv, as_of_date, league)[:max_matches]
    cutoff = pd.to_datetime(as_of_date)
    future = frame[(frame["date"] >= cutoff) & (frame["home_goals"].isna() | frame["away_goals"].isna())].sort_values("date")
    if slate_type in {"auto", "future"} and not future.empty:
        return "future_fixture_slate", [
            {"home_team": r["home_team"], "away_team": r["away_team"], "league": r.get("league"), "as_of_date": as_of_date}
            for _, r in future.head(max_matches).iterrows()
        ]
    hist = frame[frame["date"] <= cutoff].sort_values("date", ascending=False).head(max_matches).sort_values("date")
    return "historical_validation_slate", [
        {"home_team": r["home_team"], "away_team": r["away_team"], "league": r.get("league"), "as_of_date": r["date"].date().isoformat()}
        for _, r in hist.iterrows()
    ]


def build_club_slate_report(
    input_path: str | Path,
    as_of_date: str,
    league: str | None = None,
    projection_profiles: list[str] | str | None = None,
    output_dir: str | Path = "outputs/reports",
    projection_output_dir: str | Path = "outputs/projections",
    slate_type: str = "auto",
    max_matches: int = 20,
    matchups_csv: str | Path | None = None,
) -> dict[str, Any]:
    profiles = split_csv_arg(projection_profiles if isinstance(projection_profiles, str) else None, CLUB_PROFILES) if not isinstance(projection_profiles, list) else projection_profiles
    data = _load_frame(input_path)
    resolved_type, matchups = _club_candidates(data, as_of_date, league, slate_type, max_matches, matchups_csv)
    rows = []
    for matchup in matchups:
        for profile in profiles:
            row = _club_row(data, matchup["home_team"], matchup["away_team"], matchup["as_of_date"], profile, league=matchup.get("league"))
            row["slate_date"] = as_of_date
            row["slate_type"] = resolved_type
            row["league"] = matchup.get("league") or row.get("league", league)
            rows.append(row)
    result = pd.DataFrame(rows)
    for col in CLUB_SLATE_COLUMNS:
        if col not in result.columns:
            result[col] = pd.NA
    result = result[CLUB_SLATE_COLUMNS]
    csv_path = write_csv(result, Path(projection_output_dir) / "club_slate_projections.csv")
    md_path = write_markdown_report(
        Path(output_dir) / "club_slate_report.md",
        "Club Slate Projection Report",
        str(input_path),
        resolved_type,
        result,
        ["league", "home_team", "away_team", "projection_profile", "projected_total", "home_win_prob", "draw_prob", "away_win_prob", "confidence_label"],
        ["projection_profile", "baseline_mode_used", "market_influence_level", "home_xg_final", "away_xg_final", "projected_total", "most_likely_score", "confidence_label", "risk_flags", "model_market_gap_summary"],
        ("home_team", "away_team"),
        [
            "General report view highlights score_projection; winner_probability is the strongest validated W/D/L context profile from Phase 14.",
            "Data Support / Risk Context wording should be used instead of treating confidence labels as certainty.",
            "Confidence is not a betting signal, and market gap is not a betting recommendation.",
            "Proxy score adjustments remain disabled by default.",
        ],
    )
    return {"results": result, "slate_type": resolved_type, "csv_path": csv_path, "markdown_path": md_path}


def _manual_international_matchups(path: str | Path, default_date: str, default_neutral: str, default_context: str) -> list[dict[str, Any]]:
    rows = pd.read_csv(path).to_dict("records")
    return [
        {
            "team_a": row["team_a"],
            "team_b": row["team_b"],
            "neutral_site": row.get("neutral_site") or default_neutral,
            "competition_context": row.get("competition_context") or default_context,
            "as_of_date": row.get("as_of_date") or default_date,
        }
        for row in rows
    ]


def _international_candidates(data: pd.DataFrame, as_of_date: str, max_matches: int, matchups: list[dict[str, Any]] | None, matchups_csv: str | Path | None, team_a: str | None, team_b: str | None, neutral_site: str, competition_context: str) -> tuple[str, list[dict[str, Any]]]:
    if matchups:
        return "manual_matchup_slate", matchups[:max_matches]
    if matchups_csv:
        return "manual_matchup_slate", _manual_international_matchups(matchups_csv, as_of_date, neutral_site, competition_context)[:max_matches]
    if team_a and team_b:
        return "manual_matchup_slate", [{"team_a": team_a, "team_b": team_b, "neutral_site": neutral_site, "competition_context": competition_context, "as_of_date": as_of_date}]
    cutoff = pd.to_datetime(as_of_date)
    hist = data[data["date"] <= cutoff].sort_values("date", ascending=False).head(max_matches).sort_values("date")
    return "historical_validation_slate", [
        {
            "team_a": r["home_team"],
            "team_b": r["away_team"],
            "neutral_site": r.get("neutral_site", neutral_site),
            "competition_context": r.get("competition_name", competition_context),
            "as_of_date": r["date"].date().isoformat(),
        }
        for _, r in hist.iterrows()
    ]


def build_international_slate_report(
    input_path: str | Path,
    as_of_date: str,
    matchups: list[dict[str, Any]] | None = None,
    neutral_site: str = "unknown",
    projection_profiles: list[str] | str | None = None,
    output_dir: str | Path = "outputs/reports",
    projection_output_dir: str | Path = "outputs/projections",
    team_a: str | None = None,
    team_b: str | None = None,
    competition_context: str = "",
    matchups_csv: str | Path | None = None,
    max_matches: int = 20,
) -> dict[str, Any]:
    profiles = split_csv_arg(projection_profiles if isinstance(projection_profiles, str) else None, INTERNATIONAL_PROFILES) if not isinstance(projection_profiles, list) else projection_profiles
    data = _load_frame(input_path)
    resolved_type, selected = _international_candidates(data, as_of_date, max_matches, matchups, matchups_csv, team_a, team_b, neutral_site, competition_context)
    rows = []
    for matchup in selected:
        for profile in profiles:
            row = _intl_row(data, matchup["team_a"], matchup["team_b"], matchup["as_of_date"], profile, matchup.get("neutral_site", neutral_site), matchup.get("competition_context", competition_context))
            row["slate_date"] = as_of_date
            row["slate_type"] = resolved_type
            rows.append(row)
    result = pd.DataFrame(rows)
    for col in INTERNATIONAL_SLATE_COLUMNS:
        if col not in result.columns:
            result[col] = pd.NA
    result = result[INTERNATIONAL_SLATE_COLUMNS]
    csv_path = write_csv(result, Path(projection_output_dir) / "international_slate_projections.csv")
    md_path = write_markdown_report(
        Path(output_dir) / "international_slate_report.md",
        "International Slate Projection Report",
        str(input_path),
        resolved_type,
        result,
        ["team_a", "team_b", "projection_profile", "projected_total", "team_a_win_prob", "draw_prob", "team_b_win_prob", "confidence_label"],
        ["projection_profile", "baseline_mode_used", "team_a_xg_final", "team_b_xg_final", "projected_total", "most_likely_score", "confidence_label", "risk_flags", "international_context_warnings"],
        ("team_a", "team_b"),
        [
            "International outputs use national-team ratings only and do not mix club ratings.",
            "International Data Support remains conservative and context-only.",
        ],
    )
    return {"results": result, "slate_type": resolved_type, "csv_path": csv_path, "markdown_path": md_path}

