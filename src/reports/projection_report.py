from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.models.current_score_projection import project_current_match
from src.models.international_projection import project_international_match
from src.reports.report_formatting import NO_BETTING_DISCLAIMER, markdown_table, split_csv_arg, write_csv, write_markdown_report


CLUB_PROFILES = ["score_projection", "winner_probability", "total_goals", "market_anchored", "model_only"]
INTERNATIONAL_PROFILES = [
    "international_score_projection",
    "international_winner_probability",
    "international_total_goals",
    "international_event_style_context",
    "international_model_only",
]


def _infer_club_league(data: pd.DataFrame | str | Path, home: str, away: str) -> str | None:
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    if "league" not in frame.columns:
        return None
    exact = frame[(frame["home_team"].eq(home) & frame["away_team"].eq(away)) | (frame["home_team"].eq(away) & frame["away_team"].eq(home))]
    if not exact.empty and exact["league"].nunique() == 1:
        return str(exact["league"].iloc[0])
    related = frame[frame["home_team"].isin([home, away]) | frame["away_team"].isin([home, away])]
    if not related.empty and related["league"].nunique() == 1:
        return str(related["league"].iloc[0])
    return None


def _club_row(data: pd.DataFrame | str | Path, home: str, away: str, as_of_date: str, profile: str, league: str | None = None) -> dict[str, Any]:
    effective_league = league or _infer_club_league(data, home, away)
    row = project_current_match(data, home, away, as_of_date, league=effective_league, projection_profile=profile).iloc[0].to_dict()
    row["league"] = effective_league
    row["betting_recommendation"] = None
    return row


def _intl_row(data: pd.DataFrame | str | Path, team_a: str, team_b: str, as_of_date: str, profile: str, neutral_site: str, competition_context: str) -> dict[str, Any]:
    row = project_international_match(
        data,
        team_a,
        team_b,
        as_of_date,
        neutral_site=neutral_site,
        projection_profile=profile,
        competition_context=competition_context,
    ).iloc[0].to_dict()
    row["betting_recommendation"] = None
    return row


def disagreement_flags(frame: pd.DataFrame, international: bool = False) -> str:
    if frame.empty:
        return "none"
    flags: list[str] = []
    win_col = "team_a_win_prob" if international else "home_win_prob"
    xg_a = "team_a_xg_final" if international else "home_xg_final"
    xg_b = "team_b_xg_final" if international else "away_xg_final"
    if pd.to_numeric(frame[win_col], errors="coerce").max() - pd.to_numeric(frame[win_col], errors="coerce").min() >= 0.12:
        flags.append("high_winner_disagreement")
    totals = pd.to_numeric(frame["projected_total"], errors="coerce")
    if totals.max() - totals.min() >= 0.35:
        flags.append("high_total_disagreement")
    conf = pd.to_numeric(frame["confidence_score"], errors="coerce")
    if conf.max() - conf.min() >= 20:
        flags.append("high_confidence_disagreement")
    if not international and "model_market_gap_summary" in frame.columns and frame["model_market_gap_summary"].astype(str).str.contains(r"[+-]0\.(?:1|2|3|4|5|6|7|8|9)", regex=True).any():
        flags.append("market_vs_model_disagreement")
    if pd.to_numeric(frame[xg_a], errors="coerce").isna().all() or pd.to_numeric(frame[xg_b], errors="coerce").isna().all():
        flags.append("missing_projection_values")
    return " | ".join(flags) if flags else "none"


def compare_club_projection_profiles(
    input_path: str | Path,
    home: str,
    away: str,
    as_of_date: str,
    profiles: list[str] | str | None = None,
    output_dir: str | Path = "outputs/reports",
    projection_output_dir: str | Path = "outputs/projections",
    league: str | None = None,
) -> dict[str, Any]:
    selected = split_csv_arg(profiles if isinstance(profiles, str) else None, CLUB_PROFILES) if not isinstance(profiles, list) else profiles
    data = pd.read_csv(input_path)
    rows = [_club_row(data, home, away, as_of_date, profile, league=league) for profile in selected]
    frame = pd.DataFrame(rows)
    frame.insert(0, "profile_disagreement_flags", disagreement_flags(frame))
    csv_path = write_csv(frame, Path(projection_output_dir) / "projection_profile_comparison.csv")
    md_path = _write_profile_comparison_md(frame, Path(output_dir) / "projection_profile_comparison.md", f"Club Profile Comparison: {home} vs {away}", False)
    return {"results": frame, "csv_path": csv_path, "markdown_path": md_path}


def compare_international_projection_profiles(
    input_path: str | Path,
    team_a: str,
    team_b: str,
    as_of_date: str,
    neutral_site: str = "unknown",
    competition_context: str = "",
    profiles: list[str] | str | None = None,
    output_dir: str | Path = "outputs/reports",
    projection_output_dir: str | Path = "outputs/projections",
) -> dict[str, Any]:
    selected = split_csv_arg(profiles if isinstance(profiles, str) else None, INTERNATIONAL_PROFILES) if not isinstance(profiles, list) else profiles
    data = pd.read_csv(input_path)
    rows = [_intl_row(data, team_a, team_b, as_of_date, profile, neutral_site, competition_context) for profile in selected]
    frame = pd.DataFrame(rows)
    frame.insert(0, "profile_disagreement_flags", disagreement_flags(frame, international=True))
    csv_path = write_csv(frame, Path(projection_output_dir) / "projection_profile_comparison.csv")
    md_path = _write_profile_comparison_md(frame, Path(output_dir) / "projection_profile_comparison.md", f"International Profile Comparison: {team_a} vs {team_b}", True)
    return {"results": frame, "csv_path": csv_path, "markdown_path": md_path}


def _write_profile_comparison_md(frame: pd.DataFrame, path: Path, title: str, international: bool) -> Path:
    if international:
        summary = ["projection_profile", "baseline_mode_used", "team_a_xg_final", "team_b_xg_final", "projected_total", "team_a_win_prob", "draw_prob", "team_b_win_prob", "confidence_label", "confidence_score"]
        detail = summary + ["risk_flags", "international_context_warnings", "data_mode"]
        matchup_cols = ("team_a", "team_b")
    else:
        summary = ["projection_profile", "baseline_mode_used", "market_influence_level", "home_xg_final", "away_xg_final", "projected_total", "home_win_prob", "draw_prob", "away_win_prob", "confidence_label", "confidence_score"]
        detail = summary + ["risk_flags", "model_market_gap_summary", "warnings", "data_mode"]
        matchup_cols = ("home_team", "away_team")
    notes = [NO_BETTING_DISCLAIMER, f"Disagreement flags: {frame['profile_disagreement_flags'].iloc[0] if not frame.empty else 'none'}"]
    return write_markdown_report(path, title, "projection function output", "profile_comparison", frame, summary, detail, matchup_cols, notes)
