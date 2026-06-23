from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from style_features import HIGHER_IS_BETTER, STYLE_COLUMNS


METRIC_LABELS = {
    "possession_pct": "possession share",
    "field_tilt_pct": "territory/field tilt",
    "avg_possession_seconds": "possession length",
    "passes_per_possession": "pass patience",
    "central_progression_pct": "central progression share",
    "direct_speed_mps": "direct attack speed",
    "fast_attacks_per90": "fast attacks",
    "progressive_passes_per90": "progressive passing",
    "progressive_carries_per90": "progressive carrying",
    "runs_in_behind_per90": "runs behind the line",
    "avg_block_height": "defensive block height",
    "ppda": "pressing intensity PPDA",
    "high_regains_per90": "high regains",
    "opponent_box_touches_allowed": "opponent box touches allowed",
    "xga_per90": "xG allowed",
    "avg_team_width": "team width",
    "avg_team_depth": "team depth",
    "touch_x_mean": "average touch height",
    "touch_y_spread": "touch width spread",
    "sprints_per90": "sprints",
}

STYLE_TO_METRICS = {
    "control_rating": ["possession_pct", "field_tilt_pct", "avg_possession_seconds", "passes_per_possession", "central_progression_pct"],
    "verticality_rating": ["direct_speed_mps", "fast_attacks_per90", "runs_in_behind_per90", "progressive_passes_per90", "progressive_carries_per90"],
    "low_block_rating": ["avg_block_height", "opponent_box_touches_allowed", "xga_per90", "possession_pct"],
    "pressing_rating": ["avg_block_height", "ppda", "high_regains_per90", "touch_x_mean"],
    "movement_width_rating": ["avg_team_width", "touch_y_spread", "avg_team_depth"],
    "off_ball_run_rating": ["runs_in_behind_per90", "sprints_per90", "fast_attacks_per90"],
    "territory_rating": ["field_tilt_pct", "touch_x_mean", "possession_pct"],
    "defensive_resistance_rating": ["xga_per90", "opponent_box_touches_allowed", "central_progression_pct"],
    "tempo_rating": ["direct_speed_mps", "fast_attacks_per90", "sprints_per90", "avg_possession_seconds"],
}


def _fmt_value(v: float) -> str:
    if pd.isna(v):
        return "n/a"
    if abs(v) >= 20:
        return f"{v:.0f}"
    return f"{v:.2f}" if abs(v) < 10 else f"{v:.1f}"


def metric_evidence(match_log: pd.DataFrame, team: str, metrics: list[str], max_items: int = 5) -> list[str]:
    """Return human-readable evidence using team averages vs dataset averages."""
    if team not in set(match_log["team"]):
        return []

    team_rows = match_log[match_log["team"] == team]
    evidence = []
    for metric in metrics:
        if metric not in match_log.columns:
            continue
        team_avg = pd.to_numeric(team_rows[metric], errors="coerce").mean()
        all_avg = pd.to_numeric(match_log[metric], errors="coerce").mean()
        if pd.isna(team_avg) or pd.isna(all_avg):
            continue
        direction = HIGHER_IS_BETTER.get(metric, True)
        delta = team_avg - all_avg
        if not direction:
            # For allowance metrics and PPDA, lower raw values are usually stronger.
            strength_phrase = "lower than dataset avg" if delta < 0 else "higher than dataset avg"
        else:
            strength_phrase = "higher than dataset avg" if delta > 0 else "lower than dataset avg"
        evidence.append((abs(delta), f"{METRIC_LABELS.get(metric, metric)}: {_fmt_value(team_avg)} vs avg {_fmt_value(all_avg)} ({strength_phrase})"))

    evidence.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in evidence[:max_items]]


def recent_shift(match_log: pd.DataFrame, team: str) -> str:
    """Describe whether a style has recently shifted over tracked matches.

    Needs at least 4 rows to say anything; otherwise it refuses to overclaim.
    """
    rows = match_log[match_log["team"] == team].copy()
    if len(rows) < 4:
        return "Not enough matches to judge a trend yet. Treat identity as early sample."
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows = rows.sort_values("date")
    half = len(rows) // 2
    early = rows.iloc[:half]
    late = rows.iloc[half:]

    checks = []
    for metric, label in [
        ("direct_speed_mps", "direct speed"),
        ("avg_block_height", "block height"),
        ("possession_pct", "possession share"),
        ("runs_in_behind_per90", "run threat"),
    ]:
        e = pd.to_numeric(early[metric], errors="coerce").mean()
        l = pd.to_numeric(late[metric], errors="coerce").mean()
        if pd.isna(e) or pd.isna(l):
            continue
        delta = l - e
        if abs(delta) >= max(2, abs(e) * 0.08):
            direction = "up" if delta > 0 else "down"
            checks.append(f"{label} trending {direction}")
    return "; ".join(checks) if checks else "No clear recent style shift detected yet."


def load_scouting_notes(path: str | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame(columns=["team", "note", "source", "confidence", "tags"])
    try:
        notes = pd.read_csv(path)
    except FileNotFoundError:
        return pd.DataFrame(columns=["team", "note", "source", "confidence", "tags"])
    required = {"team", "note"}
    if not required.issubset(notes.columns):
        raise ValueError("Scouting notes must include at least: team,note")
    for col in ["source", "confidence", "tags"]:
        if col not in notes.columns:
            notes[col] = ""
    return notes


def notes_for_team(notes: pd.DataFrame, team: str) -> list[str]:
    if notes.empty:
        return []
    rows = notes[notes["team"].astype(str).str.lower() == team.lower()]
    out = []
    for _, r in rows.iterrows():
        conf = r.get("confidence", "")
        source = r.get("source", "")
        suffix = f" [{source}; confidence={conf}]" if source or conf else ""
        out.append(f"{r['note']}{suffix}")
    return out
