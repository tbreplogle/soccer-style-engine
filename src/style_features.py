from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

# Metric direction means: higher raw value should produce a higher 0-100 style rating.
# For defensive allowance metrics, lower raw value is better/higher.
HIGHER_IS_BETTER = {
    "possession_pct": True,
    "field_tilt_pct": True,
    "avg_possession_seconds": True,
    "passes_per_possession": True,
    "central_progression_pct": True,
    "direct_speed_mps": True,
    "fast_attacks_per90": True,
    "progressive_passes_per90": True,
    "progressive_carries_per90": True,
    "runs_in_behind_per90": True,
    "avg_block_height": True,
    "ppda": False,
    "high_regains_per90": True,
    "opponent_box_touches_allowed": False,
    "xga_per90": False,
    "avg_team_width": True,
    "avg_team_depth": True,
    "touch_x_mean": True,
    "touch_y_spread": True,
    "sprints_per90": True,
}

STYLE_COLUMNS = [
    "control_rating",
    "verticality_rating",
    "low_block_rating",
    "pressing_rating",
    "movement_width_rating",
    "off_ball_run_rating",
    "territory_rating",
    "defensive_resistance_rating",
    "tempo_rating",
]

REQUIRED_COLUMNS = ["match_id", "date", "team", "opponent", "minutes"] + list(HIGHER_IS_BETTER)


def validate_match_log(match_log: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in match_log.columns]
    if missing:
        raise ValueError(f"Match log missing required columns: {missing}")

    if match_log.empty:
        raise ValueError("Match log is empty.")

    if match_log["team"].isna().any():
        raise ValueError("Match log contains blank team names.")


def _rating(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Convert raw values to a 0-100 relative rating.

    This is intentionally relative inside the current dataset. Once the database grows,
    we will replace this with competition-adjusted baselines by league/season.
    """
    clean = pd.to_numeric(series, errors="coerce")
    if clean.nunique(dropna=True) <= 1:
        return pd.Series(50.0, index=series.index)
    ranks = clean.rank(pct=True, method="average") * 100
    if not higher_is_better:
        ranks = 100 - ranks + (100 / clean.count())
    return ranks.clip(lower=0, upper=100).round(1)


def _safe_col(df: pd.DataFrame, col: str, default: float = 50.0) -> pd.Series:
    if col in df:
        return pd.to_numeric(df[col], errors="coerce").fillna(default)
    return pd.Series(default, index=df.index)


def summarize_team_style(match_log: pd.DataFrame) -> pd.DataFrame:
    """Aggregate team match rows and calculate style identity ratings.

    This function should remain deterministic and auditable. It is the style engine's
    source of truth before any AI/LLM interpretation is added.
    """
    validate_match_log(match_log)
    match_log = match_log.copy()
    match_log["date"] = pd.to_datetime(match_log["date"], errors="coerce")

    numeric_cols = [c for c in HIGHER_IS_BETTER if c in match_log.columns]
    agg = (
        match_log.groupby("team", as_index=False)[numeric_cols]
        .mean(numeric_only=True)
        .round(3)
    )
    games = match_log.groupby("team", as_index=False).agg(
        matches_tracked=("match_id", "nunique"),
        first_match_date=("date", "min"),
        last_match_date=("date", "max"),
    )
    agg = agg.merge(games, on="team", how="left")

    # Metric-level normalized ratings.
    for col in numeric_cols:
        agg[f"{col}_r"] = _rating(agg[col], HIGHER_IS_BETTER[col])

    # Style ratings describe *how* a team plays, not only whether they are good.
    agg["control_rating"] = (
        0.30 * agg["possession_pct_r"]
        + 0.25 * agg["field_tilt_pct_r"]
        + 0.20 * agg["avg_possession_seconds_r"]
        + 0.15 * agg["passes_per_possession_r"]
        + 0.10 * agg["central_progression_pct_r"]
    ).round(1)

    agg["verticality_rating"] = (
        0.30 * agg["direct_speed_mps_r"]
        + 0.25 * agg["fast_attacks_per90_r"]
        + 0.20 * agg["runs_in_behind_per90_r"]
        + 0.15 * agg["progressive_passes_per90_r"]
        + 0.10 * agg["progressive_carries_per90_r"]
    ).round(1)

    # Low block is a style, not automatically a weakness. Lower block height,
    # lower possession, and strong box protection raise this rating.
    agg["low_block_rating"] = (
        0.30 * (100 - agg["avg_block_height_r"] + 25)
        + 0.25 * agg["opponent_box_touches_allowed_r"]
        + 0.25 * agg["xga_per90_r"]
        + 0.20 * (100 - agg["possession_pct_r"] + 25)
    ).clip(0, 100).round(1)

    agg["pressing_rating"] = (
        0.35 * agg["avg_block_height_r"]
        + 0.30 * agg["ppda_r"]
        + 0.25 * agg["high_regains_per90_r"]
        + 0.10 * agg["touch_x_mean_r"]
    ).round(1)

    agg["movement_width_rating"] = (
        0.55 * agg["avg_team_width_r"]
        + 0.30 * agg["touch_y_spread_r"]
        + 0.15 * agg["avg_team_depth_r"]
    ).round(1)

    agg["off_ball_run_rating"] = (
        0.45 * agg["runs_in_behind_per90_r"]
        + 0.30 * agg["sprints_per90_r"]
        + 0.25 * agg["fast_attacks_per90_r"]
    ).round(1)

    agg["territory_rating"] = (
        0.45 * agg["field_tilt_pct_r"]
        + 0.35 * agg["touch_x_mean_r"]
        + 0.20 * agg["possession_pct_r"]
    ).round(1)

    agg["defensive_resistance_rating"] = (
        0.45 * agg["xga_per90_r"]
        + 0.35 * agg["opponent_box_touches_allowed_r"]
        + 0.20 * agg["central_progression_pct_r"]
    ).round(1)

    agg["tempo_rating"] = (
        0.35 * agg["direct_speed_mps_r"]
        + 0.30 * agg["fast_attacks_per90_r"]
        + 0.20 * agg["sprints_per90_r"]
        + 0.15 * agg["avg_possession_seconds_r"].rsub(100)
    ).round(1)

    agg["primary_identity"] = agg.apply(classify_identity, axis=1)
    agg["style_signature"] = agg.apply(style_signature, axis=1)
    agg["identity_confidence"] = agg.apply(identity_confidence, axis=1)

    keep_cols = [
        "team",
        "matches_tracked",
        "first_match_date",
        "last_match_date",
    ] + numeric_cols + STYLE_COLUMNS + [
        "primary_identity",
        "identity_confidence",
        "style_signature",
    ]
    return agg[keep_cols].sort_values("team").reset_index(drop=True)


def classify_identity(row: pd.Series) -> str:
    """Assign a tactical identity without using team reputation or market strength."""
    if row["low_block_rating"] >= 72 and row["defensive_resistance_rating"] >= 65 and row["pressing_rating"] <= 55:
        return "Defensive Low Block"
    if row["verticality_rating"] >= 78 and row["off_ball_run_rating"] >= 72:
        return "Fast / Vertical Run Threat"
    if row["control_rating"] >= 78 and row["pressing_rating"] >= 72:
        return "Possession + High Press"
    if row["control_rating"] >= 72:
        return "Possession Controller"
    if row["pressing_rating"] >= 72:
        return "Aggressive Pressing"
    if row["verticality_rating"] >= 72:
        return "Fast / Vertical"
    if row["off_ball_run_rating"] >= 72:
        return "Off-Ball Runner"
    if row["movement_width_rating"] >= 72:
        return "Wide Field Stretcher"
    return "Balanced / Mixed"


def style_signature(row: pd.Series) -> str:
    traits = []
    if row["control_rating"] >= 70:
        traits.append("controls possession")
    if row["verticality_rating"] >= 70:
        traits.append("attacks fast and vertical")
    if row["low_block_rating"] >= 70:
        traits.append("defends deep/compact")
    if row["pressing_rating"] >= 70:
        traits.append("presses high")
    if row["off_ball_run_rating"] >= 70:
        traits.append("creates run threat")
    if row["movement_width_rating"] >= 70:
        traits.append("stretches the field")
    if row["territory_rating"] >= 70:
        traits.append("lives in opponent half")
    if not traits:
        return "mixed profile with no dominant style yet"
    return "; ".join(traits)


def identity_confidence(row: pd.Series) -> int:
    """Score how clearly a team's style separates from its next-best identity.

    This is not prediction confidence. It is confidence that the style label is real.
    """
    scores = row[STYLE_COLUMNS].astype(float).sort_values(ascending=False)
    top = scores.iloc[0]
    second = scores.iloc[1] if len(scores) > 1 else 50
    separation = max(0, top - second)
    games_bonus = min(12, float(row.get("matches_tracked", 1)) * 3)
    confidence = 45 + separation * 0.8 + games_bonus
    return int(round(max(35, min(92, confidence))))


def style_rankings(summary: pd.DataFrame, team: str) -> list[tuple[str, float]]:
    row = summary.loc[summary["team"] == team]
    if row.empty:
        raise KeyError(f"Team not found in summary: {team}")
    r = row.iloc[0]
    return sorted([(c, float(r[c])) for c in STYLE_COLUMNS], key=lambda x: x[1], reverse=True)
