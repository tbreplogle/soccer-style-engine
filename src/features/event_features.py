from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0

TEAM_MATCH_STYLE_COLUMNS = [
    "match_id",
    "date",
    "competition",
    "season",
    "team",
    "opponent",
    "is_home",
    "goals_for",
    "goals_against",
    "result",
    "possession_pct",
    "field_tilt_pct",
    "avg_possession_length",
    "direct_speed",
    "passes_completed",
    "pass_completion_pct",
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
    "counterpressures",
    "pressures",
    "high_regains",
    "ppda_proxy",
    "turnovers_own_third",
    "turnovers_middle_third",
    "defensive_block_height",
    "compactness",
    "opponent_players_between_ball_and_goal",
    "pass_options_visible",
    "central_density",
    "defensive_block_depth",
    "width_in_possession",
    "depth_in_possession",
    "set_piece_xg_for",
    "set_piece_xg_against",
    "data_quality_flag",
]


def _series(df: pd.DataFrame, name: str, default: Any = np.nan) -> pd.Series:
    if name in df.columns:
        return df[name]
    return pd.Series(default, index=df.index)


def _list_value(value: Any, idx: int) -> float:
    if isinstance(value, (list, tuple)) and len(value) > idx:
        return float(value[idx])
    return np.nan


def _event_seconds(row: pd.Series) -> float:
    if "timestamp" in row and isinstance(row["timestamp"], str):
        parts = row["timestamp"].split(":")
        if len(parts) == 3:
            try:
                h, m, s = parts
                return float(h) * 3600 + float(m) * 60 + float(s)
            except ValueError:
                pass
    return float(row.get("minute", 0) or 0) * 60 + float(row.get("second", 0) or 0)


def normalize_events(events: pd.DataFrame) -> pd.DataFrame:
    """Flatten common StatsBomb event fields and normalize coordinates.

    StatsBomb Open Data uses a 120x80 pitch. Events are treated as attacking
    left-to-right. If a team's shots are mostly recorded below midfield, that
    team's x/y coordinates are flipped as a conservative orientation correction.
    """
    if events.empty:
        return events.copy()
    df = events.copy()
    df["event_type"] = _series(df, "type.name", _series(df, "type", ""))
    df["team"] = _series(df, "team.name", _series(df, "team", ""))
    df["possession_team"] = _series(df, "possession_team.name", _series(df, "possession_team", df["team"]))
    df["x"] = _series(df, "location").apply(lambda v: _list_value(v, 0))
    df["y"] = _series(df, "location").apply(lambda v: _list_value(v, 1))

    end_locations = []
    for _, row in df.iterrows():
        if isinstance(row.get("pass.end_location"), (list, tuple)):
            end_locations.append(row.get("pass.end_location"))
        elif isinstance(row.get("carry.end_location"), (list, tuple)):
            end_locations.append(row.get("carry.end_location"))
        else:
            end_locations.append([np.nan, np.nan])
    df["end_x"] = [_list_value(v, 0) for v in end_locations]
    df["end_y"] = [_list_value(v, 1) for v in end_locations]
    df["event_seconds"] = df.apply(_event_seconds, axis=1)

    for team, rows in df.groupby("team"):
        shot_x = rows.loc[rows["event_type"].eq("Shot"), "x"].dropna()
        if not shot_x.empty and shot_x.mean() < PITCH_LENGTH / 2:
            idx = df["team"].eq(team)
            df.loc[idx, "x"] = PITCH_LENGTH - df.loc[idx, "x"]
            df.loc[idx, "end_x"] = PITCH_LENGTH - df.loc[idx, "end_x"]
            df.loc[idx, "y"] = PITCH_WIDTH - df.loc[idx, "y"]
            df.loc[idx, "end_y"] = PITCH_WIDTH - df.loc[idx, "end_y"]
    return df


def _is_completed_pass(rows: pd.DataFrame) -> pd.Series:
    return rows["event_type"].eq("Pass") & _series(rows, "pass.outcome.name").isna()


def _is_progressive(rows: pd.DataFrame) -> pd.Series:
    return (rows["end_x"] - rows["x"] >= 10) & rows["end_x"].notna()


def _is_box_entry(rows: pd.DataFrame) -> pd.Series:
    ends_in_box = (rows["end_x"] >= 102) & rows["end_y"].between(18, 62)
    starts_outside = ~((rows["x"] >= 102) & rows["y"].between(18, 62))
    return ends_in_box & starts_outside


def _result(goals_for: int, goals_against: int) -> str:
    if goals_for > goals_against:
        return "W"
    if goals_for < goals_against:
        return "L"
    return "D"


def _infer_goals(events: pd.DataFrame, team: str) -> int:
    shots = events[events["event_type"].eq("Shot") & events["team"].eq(team)]
    return int(_series(shots, "shot.outcome.name", "").astype(str).str.lower().eq("goal").sum())


def _avg_possession_length(events: pd.DataFrame, team: str) -> float:
    if "possession" not in events.columns:
        return float("nan")
    poss = events[events["possession_team"].eq(team)].groupby("possession")["event_seconds"].agg(["min", "max"])
    if poss.empty:
        return float("nan")
    lengths = (poss["max"] - poss["min"]).clip(lower=0)
    return float(lengths.mean())


def _fast_attacks(events: pd.DataFrame, team: str) -> int:
    if "possession" not in events.columns:
        return 0
    count = 0
    for _, rows in events[events["possession_team"].eq(team)].groupby("possession"):
        length = rows["event_seconds"].max() - rows["event_seconds"].min()
        if length <= 15 and (rows["event_type"].eq("Shot").any() or _is_box_entry(rows).any()):
            count += 1
    return count


def _set_piece_xg(shots: pd.DataFrame) -> float:
    if shots.empty:
        return 0.0
    pattern = _series(shots, "play_pattern.name", "").astype(str).str.lower()
    is_set_piece = pattern.str.contains("corner|free kick|throw|set piece", regex=True)
    return float(pd.to_numeric(_series(shots.loc[is_set_piece], "shot.statsbomb_xg", 0), errors="coerce").fillna(0).sum())


def _extract_360_metrics(three_sixty: pd.DataFrame | None) -> dict[str, float | None]:
    if three_sixty is None or three_sixty.empty or "freeze_frame" not in three_sixty.columns:
        return {
            "compactness": None,
            "width_in_possession": None,
            "depth_in_possession": None,
            "pass_options_visible": None,
            "central_density": None,
            "defensive_block_height": None,
            "defensive_block_depth": None,
            "opponent_players_between_ball_and_goal": None,
        }
    widths = []
    depths = []
    compactness = []
    central_density = []
    pass_options = []
    line_heights = []
    opponent_between = []
    opponent_depth = []
    for frame in three_sixty["freeze_frame"]:
        if not isinstance(frame, list) or not frame:
            continue
        locs = [p.get("location") for p in frame if isinstance(p, Mapping) and isinstance(p.get("location"), list)]
        if not locs:
            continue
        xs = np.array([loc[0] for loc in locs], dtype=float)
        ys = np.array([loc[1] for loc in locs], dtype=float)
        widths.append(float(np.nanmax(ys) - np.nanmin(ys)))
        depths.append(float(np.nanmax(xs) - np.nanmin(xs)))
        compactness.append(float(np.nanstd(xs) + np.nanstd(ys)))
        central_density.append(float(((ys >= 30) & (ys <= 50)).sum()))
        pass_options.append(float(sum(1 for p in frame if isinstance(p, Mapping) and p.get("teammate"))))
        line_heights.append(float(np.nanmedian(xs)))
        opponents = [p.get("location") for p in frame if isinstance(p, Mapping) and not p.get("teammate") and isinstance(p.get("location"), list)]
        if opponents:
            ox = np.array([loc[0] for loc in opponents], dtype=float)
            opponent_between.append(float((ox >= 60).sum()))
            opponent_depth.append(float(np.nanmax(ox) - np.nanmin(ox)))
    return {
        "compactness": float(np.nanmean(compactness)) if compactness else None,
        "width_in_possession": float(np.nanmean(widths)) if widths else None,
        "depth_in_possession": float(np.nanmean(depths)) if depths else None,
        "pass_options_visible": float(np.nanmean(pass_options)) if pass_options else None,
        "central_density": float(np.nanmean(central_density)) if central_density else None,
        "defensive_block_height": float(np.nanmean(line_heights)) if line_heights else None,
        "defensive_block_depth": float(np.nanmean(opponent_depth)) if opponent_depth else None,
        "opponent_players_between_ball_and_goal": float(np.nanmean(opponent_between)) if opponent_between else None,
    }


def compute_match_style_metrics(
    events: pd.DataFrame,
    match_info: dict[str, Any] | None = None,
    three_sixty: pd.DataFrame | None = None,
) -> pd.DataFrame:
    events = normalize_events(events)
    match_info = match_info or {}
    teams = sorted(t for t in events["team"].dropna().unique() if str(t))
    metrics_360 = _extract_360_metrics(three_sixty)
    data_quality_flag = "event_plus_360" if three_sixty is not None and not three_sixty.empty else "event_only"
    rows = []

    for team in teams:
        opponent = next((t for t in teams if t != team), "")
        team_events = events[events["team"].eq(team)]
        opp_events = events[events["team"].eq(opponent)] if opponent else events.iloc[0:0]
        team_poss_events = events[events["possession_team"].eq(team)]
        passes = team_events[team_events["event_type"].eq("Pass")]
        carries = team_events[team_events["event_type"].eq("Carry")]
        completed_passes = passes[_is_completed_pass(passes)]
        shots = team_events[team_events["event_type"].eq("Shot")]
        opp_shots = opp_events[opp_events["event_type"].eq("Shot")]
        defensive_events = team_events[team_events["event_type"].isin(["Pressure", "Ball Recovery", "Interception", "Duel", "Block", "Clearance"])]
        high_def_actions = defensive_events[defensive_events["x"] >= 72]
        total_poss_events = max(1, len(events[events["possession_team"].notna()]))
        field_events = events[events["x"] >= 80]
        team_field_events = field_events[field_events["possession_team"].eq(team)]
        all_passes_completed = int(_is_completed_pass(events).sum())

        goals_for = int(match_info.get(f"{team}_goals", match_info.get("home_goals" if team == match_info.get("home_team") else "away_goals", _infer_goals(events, team))))
        goals_against = int(match_info.get(f"{opponent}_goals", match_info.get("away_goals" if team == match_info.get("home_team") else "home_goals", _infer_goals(events, opponent))))
        xg_for = float(pd.to_numeric(_series(shots, "shot.statsbomb_xg", 0), errors="coerce").fillna(0).sum())
        xg_against = float(pd.to_numeric(_series(opp_shots, "shot.statsbomb_xg", 0), errors="coerce").fillna(0).sum())
        sot = _series(shots, "shot.outcome.name", "").astype(str).str.lower().isin(["goal", "saved", "saved to post"]).sum()
        turnovers = team_events[team_events["event_type"].isin(["Dispossessed", "Miscontrol"])]
        incomplete_passes = passes[~_is_completed_pass(passes)]
        turnovers = pd.concat([turnovers, incomplete_passes], ignore_index=True)
        def_height = float(defensive_events["x"].median()) if not defensive_events.empty else np.nan
        if metrics_360["defensive_block_height"] is not None:
            def_height = float(metrics_360["defensive_block_height"])

        rows.append({
            "match_id": match_info.get("match_id", ""),
            "date": match_info.get("date", ""),
            "competition": match_info.get("competition", ""),
            "season": match_info.get("season", ""),
            "team": team,
            "opponent": opponent,
            "is_home": bool(team == match_info.get("home_team")) if match_info.get("home_team") else None,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "result": _result(goals_for, goals_against),
            "possession_pct": round(len(team_poss_events) / total_poss_events * 100, 3),
            "field_tilt_pct": round(len(team_field_events) / max(1, len(field_events)) * 100, 3),
            "avg_possession_length": round(_avg_possession_length(events, team), 3),
            "direct_speed": round(float((team_events["end_x"] - team_events["x"]).clip(lower=0).mean()), 3),
            "passes_completed": int(len(completed_passes)),
            "pass_completion_pct": round(len(completed_passes) / max(1, len(passes)) * 100, 3),
            "progressive_passes": int((_is_progressive(passes) & _is_completed_pass(passes)).sum()),
            "progressive_carries": int(_is_progressive(carries).sum()),
            "final_third_entries": int(((team_events["end_x"] >= 80) & (team_events["x"] < 80)).sum()),
            "box_entries": int(_is_box_entry(team_events).sum()),
            "runs_behind_proxy": int((_is_box_entry(passes) | _series(passes, "pass.technique.name", "").astype(str).str.contains("Through", case=False, na=False)).sum()),
            "fast_attack_count": _fast_attacks(events, team),
            "shots": int(len(shots)),
            "shots_on_target": int(sot),
            "xg_for": round(xg_for, 4),
            "xg_against": round(xg_against, 4),
            "counterpressures": int(pd.Series(_series(team_events, "counterpress", False)).fillna(False).astype(bool).sum()),
            "pressures": int(team_events["event_type"].eq("Pressure").sum()),
            "high_regains": int(high_def_actions["event_type"].isin(["Ball Recovery", "Interception"]).sum()),
            "ppda_proxy": round(int(opp_events["event_type"].eq("Pass").sum()) / max(1, len(high_def_actions)), 3),
            "turnovers_own_third": int(turnovers["x"].lt(40).sum()),
            "turnovers_middle_third": int(turnovers["x"].between(40, 80, inclusive="left").sum()),
            "defensive_block_height": round(def_height, 3) if pd.notna(def_height) else np.nan,
            "compactness": metrics_360["compactness"],
            "opponent_players_between_ball_and_goal": metrics_360["opponent_players_between_ball_and_goal"],
            "pass_options_visible": metrics_360["pass_options_visible"],
            "central_density": metrics_360["central_density"],
            "defensive_block_depth": metrics_360["defensive_block_depth"],
            "width_in_possession": metrics_360["width_in_possession"],
            "depth_in_possession": metrics_360["depth_in_possession"],
            "set_piece_xg_for": round(_set_piece_xg(shots), 4),
            "set_piece_xg_against": round(_set_piece_xg(opp_shots), 4),
            "data_quality_flag": data_quality_flag,
        })

    return pd.DataFrame(rows, columns=TEAM_MATCH_STYLE_COLUMNS)


def build_team_match_style_log(
    matches: pd.DataFrame,
    statsbomb_loader: Any,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    frames = []
    for _, match in matches.iterrows():
        match_id = match.get("match_id")
        events = statsbomb_loader.load_events(match_id)
        three_sixty = statsbomb_loader.load_360(match_id) if statsbomb_loader.match_has_360(match_id) else None
        info = {
            "match_id": match_id,
            "date": match.get("match_date", match.get("date", "")),
            "competition": match.get("competition.competition_name", match.get("competition", "")),
            "season": match.get("season.season_name", match.get("season", "")),
            "home_team": match.get("home_team.home_team_name", match.get("home_team", "")),
            "away_team": match.get("away_team.away_team_name", match.get("away_team", "")),
            "home_goals": match.get("home_score", match.get("home_goals", 0)),
            "away_goals": match.get("away_score", match.get("away_goals", 0)),
        }
        frames.append(compute_match_style_metrics(events, match_info=info, three_sixty=three_sixty))
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=TEAM_MATCH_STYLE_COLUMNS)
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
    return result
