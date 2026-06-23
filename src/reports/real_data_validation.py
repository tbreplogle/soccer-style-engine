from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.data_ingestion.statsbomb_loader import StatsBombLoader
from src.features.event_features import TEAM_MATCH_STYLE_COLUMNS, build_team_match_style_log

TRACKING_METRICS = [
    "compactness",
    "opponent_players_between_ball_and_goal",
    "pass_options_visible",
    "central_density",
    "defensive_block_depth",
    "width_in_possession",
    "depth_in_possession",
]

TOP_BOTTOM_METRICS = [
    "possession_pct",
    "direct_speed",
    "field_tilt_pct",
    "progressive_passes",
    "pressures",
    "high_regains",
    "xg_for",
]

COUNT_METRICS = [
    "progressive_passes",
    "progressive_carries",
    "final_third_entries",
    "box_entries",
    "runs_behind_proxy",
    "fast_attack_count",
    "shots",
    "shots_on_target",
    "pressures",
    "high_regains",
    "turnovers_own_third",
    "turnovers_middle_third",
]


def list_available_real_data(statsbomb_root: str | Path) -> pd.DataFrame:
    """Return available competitions/seasons from local StatsBomb Open Data."""
    loader = StatsBombLoader(statsbomb_root)
    competitions = loader.list_competitions()
    keep = [
        col
        for col in [
            "competition_id",
            "season_id",
            "competition_name",
            "season_name",
            "country_name",
            "competition_gender",
        ]
        if col in competitions.columns
    ]
    return competitions[keep] if keep else competitions


def _first_available_competition(available: pd.DataFrame) -> tuple[Any, Any]:
    if available.empty:
        raise ValueError("No competitions found in StatsBomb root.")
    if "competition_id" not in available.columns or "season_id" not in available.columns:
        raise ValueError("competitions.json must include competition_id and season_id.")
    first = available.iloc[0]
    return first["competition_id"], first["season_id"]


def select_validation_matches(
    statsbomb_root: str | Path,
    competition_id: int | str | None = None,
    season_id: int | str | None = None,
    max_matches: int = 10,
) -> pd.DataFrame:
    """Select a small validation match set from whatever real data exists locally."""
    loader = StatsBombLoader(statsbomb_root)
    available = list_available_real_data(statsbomb_root)
    if competition_id is None or season_id is None:
        competition_id, season_id = _first_available_competition(available)
    matches = loader.list_matches(competition_id, season_id)
    if matches.empty:
        return matches
    matches = matches.sort_values([c for c in ["match_date", "match_id"] if c in matches.columns])
    return matches.head(max_matches).reset_index(drop=True)


def summarize_metric_coverage(style_log: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in TEAM_MATCH_STYLE_COLUMNS:
        if col not in style_log.columns:
            continue
        non_null = int(style_log[col].notna().sum())
        rows.append({
            "metric": col,
            "non_null_rows": non_null,
            "total_rows": int(len(style_log)),
            "coverage_pct": round(non_null / max(1, len(style_log)) * 100, 1),
        })
    return pd.DataFrame(rows)


def summarize_data_quality(style_log: pd.DataFrame) -> pd.DataFrame:
    if "data_quality_flag" not in style_log.columns or style_log.empty:
        return pd.DataFrame(columns=["data_quality_flag", "rows"])
    return (
        style_log["data_quality_flag"]
        .fillna("missing")
        .value_counts()
        .rename_axis("data_quality_flag")
        .reset_index(name="rows")
    )


def missing_tracking_metrics(style_log: pd.DataFrame) -> list[str]:
    missing = []
    for metric in TRACKING_METRICS:
        if metric not in style_log.columns or style_log[metric].isna().all():
            missing.append(metric)
    return missing


def run_sanity_checks(style_log: pd.DataFrame, matches_loaded: int) -> list[str]:
    warnings: list[str] = []
    if matches_loaded == 0:
        warnings.append("No matches loaded.")
    if "team" not in style_log.columns or style_log.empty or style_log["team"].nunique() <= 1:
        warnings.append("Only one or zero teams found.")
    if "possession_pct" not in style_log.columns or style_log["possession_pct"].isna().all():
        warnings.append("All possession values are null.")
    if "xg_for" not in style_log.columns or style_log["xg_for"].isna().all() or (style_log["xg_for"].fillna(0) == 0).all():
        warnings.append("xG is missing or zero for every team-match row.")
    for metric in ["field_tilt_pct", "possession_pct"]:
        if metric in style_log.columns:
            bad = style_log[metric].dropna()
            if ((bad < 0) | (bad > 100)).any():
                warnings.append(f"{metric} contains values outside 0-100.")
    for metric in COUNT_METRICS:
        if metric in style_log.columns and (pd.to_numeric(style_log[metric], errors="coerce").dropna() < 0).any():
            warnings.append(f"{metric} contains negative counts.")
    expected_rows = matches_loaded * 2
    if len(style_log) != expected_rows:
        warnings.append(f"Team-match row count {len(style_log)} does not equal 2 x matches loaded ({expected_rows}).")
    return warnings


def team_style_summaries(style_log: pd.DataFrame) -> pd.DataFrame:
    metrics = [m for m in TOP_BOTTOM_METRICS if m in style_log.columns]
    if style_log.empty or not metrics:
        return pd.DataFrame(columns=["team", "matches"] + metrics)
    grouped = style_log.groupby("team", as_index=False).agg(matches=("match_id", "nunique"))
    means = style_log.groupby("team", as_index=False)[metrics].mean(numeric_only=True).round(3)
    return grouped.merge(means, on="team", how="left").sort_values("team")


def _markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "_No rows._"
    shown = df.head(max_rows).fillna("")
    cols = [str(c) for c in shown.columns]
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in shown.iterrows():
        values = [str(row[col]).replace("|", "/") for col in shown.columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _top_bottom_markdown(style_log: pd.DataFrame) -> str:
    lines: list[str] = []
    for metric in TOP_BOTTOM_METRICS:
        if metric not in style_log.columns or style_log[metric].dropna().empty:
            lines.extend([f"### {metric}", "", "_No non-null values._", ""])
            continue
        cols = ["team", "opponent", "match_id", metric]
        top = style_log[cols].sort_values(metric, ascending=False).head(3)
        bottom = style_log[cols].sort_values(metric, ascending=True).head(3)
        lines.extend([
            f"### {metric}",
            "",
            "**Top examples**",
            "",
            _markdown_table(top, 3),
            "",
            "**Bottom examples**",
            "",
            _markdown_table(bottom, 3),
            "",
        ])
    return "\n".join(lines)


def build_validation_report(
    available: pd.DataFrame,
    matches: pd.DataFrame,
    style_log: pd.DataFrame,
    coverage: pd.DataFrame,
    quality: pd.DataFrame,
    sanity_warnings: list[str],
) -> str:
    missing_tracking = missing_tracking_metrics(style_log)
    summaries = team_style_summaries(style_log)
    warnings = sanity_warnings.copy()
    if missing_tracking:
        warnings.append("360/tracking-aware fields are missing or nullable: " + ", ".join(missing_tracking))
    if quality["data_quality_flag"].astype(str).str.contains("event_only").any() if not quality.empty else False:
        warnings.append("Some or all matches are event_only; do not make tracking/off-ball claims as facts.")
    warnings.append("Proxy metrics include runs_behind_proxy, ppda_proxy, direct_speed, field_tilt_pct, and high_regains.")

    lines = [
        "# Real Data Validation Summary",
        "",
        "This report validates measurable style extraction. It is not a betting report.",
        "",
        "## Competitions/Seasons Inspected",
        "",
        _markdown_table(available, 25),
        "",
        "## Validation Set",
        "",
        f"Matches loaded: {len(matches)}",
        "",
        f"Team-match rows created: {len(style_log)}",
        "",
        "## Metric Coverage",
        "",
        _markdown_table(coverage, 80),
        "",
        "## Data Quality Flags",
        "",
        _markdown_table(quality),
        "",
        "## Team-Level Style Summaries",
        "",
        _markdown_table(summaries, 30),
        "",
        "## Top/Bottom Metric Examples",
        "",
        _top_bottom_markdown(style_log),
        "## Warnings",
        "",
    ]
    lines.extend([f"- {warning}" for warning in warnings] or ["- No validation warnings."])
    lines.extend([
        "",
        "## Recommended Next Validation Step",
        "",
        "Run the validator on 25-50 real matches from one competition/season, then review whether metric ranges and identity labels match only the measured evidence.",
        "",
    ])
    return "\n".join(lines)


def run_real_data_validation(
    statsbomb_root: str | Path,
    competition_id: int | str | None = None,
    season_id: int | str | None = None,
    max_matches: int = 10,
    output_dir: str | Path = "outputs/reports",
) -> dict[str, Any]:
    loader = StatsBombLoader(statsbomb_root)
    available = list_available_real_data(statsbomb_root)
    matches = select_validation_matches(
        statsbomb_root,
        competition_id=competition_id,
        season_id=season_id,
        max_matches=max_matches,
    )
    style_log = build_team_match_style_log(matches, loader)
    coverage = summarize_metric_coverage(style_log)
    quality = summarize_data_quality(style_log)
    sanity_warnings = run_sanity_checks(style_log, matches_loaded=len(matches))
    report = build_validation_report(available, matches, style_log, coverage, quality, sanity_warnings)

    output_path = Path(output_dir) / "real_data_validation_summary.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    return {
        "available": available,
        "matches": matches,
        "style_log": style_log,
        "coverage": coverage,
        "quality": quality,
        "sanity_warnings": sanity_warnings,
        "report": report,
        "report_path": output_path,
    }
