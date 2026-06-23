from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.config import TEAM_MATCH_STYLE_LOG_PATH, TEAM_STYLE_PROFILES_PATH
from src.features.normalization import percentile_ranks, z_scores

PROFILE_METRICS = [
    "possession_pct",
    "field_tilt_pct",
    "avg_possession_length",
    "direct_speed",
    "progressive_passes",
    "progressive_carries",
    "final_third_entries",
    "box_entries",
    "runs_behind_proxy",
    "fast_attack_count",
    "shots",
    "shots_on_target",
    "xg_for",
    "xg_against",
    "pressures",
    "high_regains",
    "ppda_proxy",
    "turnovers_own_third",
    "turnovers_middle_third",
    "defensive_block_height",
    "compactness",
    "width_in_possession",
    "depth_in_possession",
    "set_piece_xg_for",
    "set_piece_xg_against",
]


def _load_log(style_log: pd.DataFrame | str | Path | None = None) -> pd.DataFrame:
    if style_log is None:
        return pd.read_csv(TEAM_MATCH_STYLE_LOG_PATH)
    if isinstance(style_log, pd.DataFrame):
        return style_log.copy()
    return pd.read_csv(style_log)


def _weighted_mean(values: pd.Series, weights: np.ndarray) -> float:
    vals = pd.to_numeric(values, errors="coerce")
    mask = vals.notna()
    if not mask.any():
        return float("nan")
    return float(np.average(vals[mask], weights=weights[mask.to_numpy()]))


def build_team_style_profile(
    team: str,
    as_of_date: str,
    n_matches: int = 8,
    decay: float = 0.85,
    style_log: pd.DataFrame | str | Path | None = None,
) -> dict[str, Any]:
    """Build a rolling profile using only matches before as_of_date."""
    log = _load_log(style_log)
    log["date"] = pd.to_datetime(log["date"], errors="coerce")
    as_of = pd.to_datetime(as_of_date)
    history = log[(log["team"].eq(team)) & (log["date"] < as_of)].sort_values("date").tail(n_matches)
    rows_before = log[log["date"] < as_of].copy()
    if history.empty:
        return {
            "team": team,
            "as_of_date": as_of.date().isoformat(),
            "matches_used": 0,
            "raw_metrics": {},
            "z_scores": {},
            "percentile_ranks": {},
            "data_quality_summary": "no_prior_matches",
        }

    newest_first = np.arange(len(history) - 1, -1, -1)
    weights = np.power(decay, newest_first)
    raw_metrics = {metric: _weighted_mean(history[metric], weights) for metric in PROFILE_METRICS if metric in history.columns}
    z = {}
    pct = {}
    for metric, value in raw_metrics.items():
        if metric not in rows_before.columns:
            continue
        ref = pd.to_numeric(rows_before[metric], errors="coerce")
        std = ref.std(ddof=0)
        z[metric] = 0.0 if pd.isna(std) or std == 0 or pd.isna(value) else float((value - ref.mean()) / std)
        pct_series = percentile_ranks(pd.concat([ref, pd.Series([value])], ignore_index=True))
        pct[metric] = float(pct_series.iloc[-1])

    quality_counts = history["data_quality_flag"].fillna("unknown").value_counts().to_dict() if "data_quality_flag" in history else {}
    return {
        "team": team,
        "as_of_date": as_of.date().isoformat(),
        "matches_used": int(len(history)),
        "raw_metrics": raw_metrics,
        "z_scores": z,
        "percentile_ranks": pct,
        "data_quality_summary": quality_counts,
    }


def build_all_team_style_profiles(
    as_of_date: str,
    n_matches: int = 8,
    decay: float = 0.85,
    style_log: pd.DataFrame | str | Path | None = None,
    output_path: str | Path = TEAM_STYLE_PROFILES_PATH,
) -> pd.DataFrame:
    log = _load_log(style_log)
    teams = sorted(log["team"].dropna().unique())
    rows = []
    for team in teams:
        profile = build_team_style_profile(team, as_of_date, n_matches=n_matches, decay=decay, style_log=log)
        row = {
            "team": profile["team"],
            "as_of_date": profile["as_of_date"],
            "matches_used": profile["matches_used"],
            "data_quality_summary": str(profile["data_quality_summary"]),
        }
        for metric, value in profile["raw_metrics"].items():
            row[metric] = value
            row[f"{metric}_z"] = profile["z_scores"].get(metric)
            row[f"{metric}_pctile"] = profile["percentile_ranks"].get(metric)
        rows.append(row)
    result = pd.DataFrame(rows)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    return result
