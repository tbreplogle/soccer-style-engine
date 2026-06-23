from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd

from src.data_ingestion.football_data_current import normalize_current_football_data
from src.data_ingestion.statsbomb_loader import StatsBombLoader
from src.models.international_readiness import _looks_international


INTERNATIONAL_MATCH_COLUMNS = [
    "match_id",
    "date",
    "competition_id",
    "competition_name",
    "season_id",
    "season_name",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "neutral_site",
    "match_stage",
    "tournament_round",
    "country_or_team_type",
    "data_source",
    "has_event_data",
    "has_360_data",
    "data_mode",
    "home_xg_event",
    "away_xg_event",
    "home_shots_event",
    "away_shots_event",
    "home_shots_on_target_event",
    "away_shots_on_target_event",
    "home_pressures_event",
    "away_pressures_event",
    "home_progressive_passes_event",
    "away_progressive_passes_event",
    "home_field_tilt_proxy",
    "away_field_tilt_proxy",
    "event_style_flags",
]


def _value(row: pd.Series, names: list[str], default: Any = pd.NA) -> Any:
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return default


def list_international_competitions(statsbomb_root: str | Path = "data/raw/statsbomb-open-data/data") -> pd.DataFrame:
    loader = StatsBombLoader(statsbomb_root)
    try:
        comps = loader.list_competitions()
    except FileNotFoundError:
        return pd.DataFrame(columns=["competition_id", "season_id", "competition_name", "season_name"])
    name_col = "competition_name"
    return comps[comps[name_col].fillna("").map(_looks_international)].copy() if name_col in comps.columns else pd.DataFrame()


def _match_stage(row: pd.Series) -> str:
    return str(_value(row, ["competition_stage.name", "competition_stage"], "unknown"))


def _neutral_site(row: pd.Series) -> str:
    value = _value(row, ["neutral_site", "metadata.neutral_site"], pd.NA)
    if pd.isna(value):
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return "true"
    if text in {"false", "0", "no"}:
        return "false"
    return "unknown"


def _event_metrics(events: pd.DataFrame, home_team: str, away_team: str) -> dict[str, Any]:
    if events.empty:
        return {}
    team_col = "team.name" if "team.name" in events.columns else "team"
    type_col = "type.name" if "type.name" in events.columns else "type"
    outcome_col = "shot.outcome.name"
    xg_col = "shot.statsbomb_xg"
    rows: dict[str, Any] = {}
    for side, team in [("home", home_team), ("away", away_team)]:
        team_events = events[events[team_col].eq(team)] if team_col in events.columns else pd.DataFrame()
        shots = team_events[team_events[type_col].eq("Shot")] if type_col in team_events.columns else pd.DataFrame()
        rows[f"{side}_xg_event"] = float(pd.to_numeric(shots.get(xg_col, pd.Series(dtype=float)), errors="coerce").sum()) if xg_col in shots else pd.NA
        rows[f"{side}_shots_event"] = int(len(shots))
        rows[f"{side}_shots_on_target_event"] = int(shots[outcome_col].isin(["Goal", "Saved", "Saved to Post"]).sum()) if outcome_col in shots else pd.NA
        rows[f"{side}_pressures_event"] = int(team_events[type_col].eq("Pressure").sum()) if type_col in team_events else pd.NA
        rows[f"{side}_progressive_passes_event"] = _progressive_passes(team_events)
        rows[f"{side}_field_tilt_proxy"] = _field_tilt(team_events)
    total_tilt = sum(v for v in [rows.get("home_field_tilt_proxy"), rows.get("away_field_tilt_proxy")] if pd.notna(v))
    if total_tilt > 0:
        rows["home_field_tilt_proxy"] = round(float(rows["home_field_tilt_proxy"]) / total_tilt, 4)
        rows["away_field_tilt_proxy"] = round(float(rows["away_field_tilt_proxy"]) / total_tilt, 4)
    return rows


def _event_metrics_from_file(path: Path, home_team: str, away_team: str) -> dict[str, Any]:
    events = json.loads(path.read_text(encoding="utf-8"))
    rows: dict[str, Any] = {}
    for side, team in [("home", home_team), ("away", away_team)]:
        team_events = [event for event in events if ((event.get("team") or {}).get("name") == team)]
        shots = [event for event in team_events if (event.get("type") or {}).get("name") == "Shot"]
        rows[f"{side}_xg_event"] = round(sum(float((shot.get("shot") or {}).get("statsbomb_xg") or 0) for shot in shots), 4)
        rows[f"{side}_shots_event"] = len(shots)
        rows[f"{side}_shots_on_target_event"] = sum(1 for shot in shots if ((shot.get("shot") or {}).get("outcome") or {}).get("name") in {"Goal", "Saved", "Saved to Post"})
        rows[f"{side}_pressures_event"] = sum(1 for event in team_events if (event.get("type") or {}).get("name") == "Pressure")
        rows[f"{side}_progressive_passes_event"] = _progressive_passes_raw(team_events)
        rows[f"{side}_field_tilt_proxy"] = sum(1 for event in team_events if isinstance(event.get("location"), list) and event["location"] and float(event["location"][0]) >= 80)
    total_tilt = float(rows.get("home_field_tilt_proxy", 0) + rows.get("away_field_tilt_proxy", 0))
    if total_tilt > 0:
        rows["home_field_tilt_proxy"] = round(float(rows["home_field_tilt_proxy"]) / total_tilt, 4)
        rows["away_field_tilt_proxy"] = round(float(rows["away_field_tilt_proxy"]) / total_tilt, 4)
    return rows


def _progressive_passes_raw(events: list[dict[str, Any]]) -> int:
    count = 0
    for event in events:
        if (event.get("type") or {}).get("name") != "Pass":
            continue
        start = event.get("location")
        end = (event.get("pass") or {}).get("end_location")
        if isinstance(start, list) and isinstance(end, list) and len(start) >= 2 and len(end) >= 2 and float(end[0]) - float(start[0]) >= 25:
            count += 1
    return count


def _progressive_passes(events: pd.DataFrame) -> Any:
    if "type.name" not in events or "location" not in events or "pass.end_location" not in events:
        return pd.NA
    passes = events[events["type.name"].eq("Pass")]
    count = 0
    for _, row in passes.iterrows():
        start = row.get("location")
        end = row.get("pass.end_location")
        if isinstance(start, list) and isinstance(end, list) and len(start) >= 2 and len(end) >= 2 and float(end[0]) - float(start[0]) >= 25:
            count += 1
    return count


def _field_tilt(events: pd.DataFrame) -> Any:
    if "location" not in events:
        return pd.NA
    count = 0
    for loc in events["location"].dropna():
        if isinstance(loc, list) and loc and float(loc[0]) >= 80:
            count += 1
    return count


def build_international_match_dataset(
    statsbomb_root: str | Path = "data/raw/statsbomb-open-data/data",
    output_path: str | Path | None = None,
    competition_name: str | None = None,
    competition_id: int | str | None = None,
    season_id: int | str | None = None,
    max_matches: int | None = None,
    include_football_data_folder: str | Path | None = "data/raw/football-data/international",
) -> pd.DataFrame:
    loader = StatsBombLoader(statsbomb_root)
    comps = list_international_competitions(statsbomb_root)
    if competition_name:
        comps = comps[comps["competition_name"].astype(str).str.contains(competition_name, case=False, na=False)]
    if competition_id is not None:
        comps = comps[comps["competition_id"].astype(str).eq(str(competition_id))]
    if season_id is not None:
        comps = comps[comps["season_id"].astype(str).eq(str(season_id))]
    rows: list[dict[str, Any]] = []
    for _, comp in comps.iterrows():
        try:
            matches = loader.list_matches(comp["competition_id"], comp["season_id"]).sort_values("match_date")
        except FileNotFoundError:
            continue
        if max_matches is not None:
            remaining = max_matches - len(rows)
            if remaining <= 0:
                break
            matches = matches.head(remaining)
        for _, match in matches.iterrows():
            match_id = str(_value(match, ["match_id"]))
            home = str(_value(match, ["home_team.home_team_name", "home_team.name", "home_team"], ""))
            away = str(_value(match, ["away_team.away_team_name", "away_team.name", "away_team"], ""))
            has_event = (Path(statsbomb_root) / "events" / f"{match_id}.json").exists()
            has_360 = loader.match_has_360(match_id)
            metrics = {}
            if has_event:
                try:
                    metrics = _event_metrics_from_file(Path(statsbomb_root) / "events" / f"{match_id}.json", home, away)
                except (FileNotFoundError, json.JSONDecodeError):
                    metrics = {}
            flags = [] if has_event else ["missing_event_data"]
            if not has_360:
                flags.append("missing_360_data")
            row = {
                "match_id": match_id,
                "date": str(_value(match, ["match_date", "date"], "")),
                "competition_id": comp["competition_id"],
                "competition_name": comp["competition_name"],
                "season_id": comp["season_id"],
                "season_name": comp.get("season_name", ""),
                "home_team": home,
                "away_team": away,
                "home_score": pd.to_numeric(_value(match, ["home_score"], pd.NA), errors="coerce"),
                "away_score": pd.to_numeric(_value(match, ["away_score"], pd.NA), errors="coerce"),
                "neutral_site": _neutral_site(match),
                "match_stage": _match_stage(match),
                "tournament_round": _match_stage(match),
                "country_or_team_type": "national_team",
                "data_source": "statsbomb_open_data_historical",
                "has_event_data": bool(has_event),
                "has_360_data": bool(has_360),
                "data_mode": "true_event_style_historical" if has_event else "historical_match_results",
                "event_style_flags": "|".join(flags) if flags else "event_data_available",
            }
            row.update({col: metrics.get(col, pd.NA) for col in INTERNATIONAL_MATCH_COLUMNS if col.endswith("_event") or col.endswith("_proxy")})
            rows.append(row)
    result = pd.DataFrame(rows, columns=INTERNATIONAL_MATCH_COLUMNS)
    fd_rows = load_optional_international_football_data(include_football_data_folder)
    if not fd_rows.empty:
        result = pd.concat([result, fd_rows], ignore_index=True)
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
    return result


def load_optional_international_football_data(folder: str | Path | None) -> pd.DataFrame:
    if folder is None:
        return pd.DataFrame(columns=INTERNATIONAL_MATCH_COLUMNS)
    root = Path(folder)
    if not root.exists():
        return pd.DataFrame(columns=INTERNATIONAL_MATCH_COLUMNS)
    frames = []
    for path in sorted(root.glob("*.csv")):
        raw = pd.read_csv(path)
        if not {"Date", "HomeTeam", "AwayTeam"}.issubset(raw.columns):
            continue
        norm = normalize_current_football_data(raw, league="INTL", season="", data_source=str(path))
        frame = pd.DataFrame({
            "match_id": norm["match_id"],
            "date": norm["date"],
            "competition_id": "football_data_international",
            "competition_name": "Football-Data International",
            "season_id": "",
            "season_name": "",
            "home_team": norm["home_team"],
            "away_team": norm["away_team"],
            "home_score": norm["home_goals"],
            "away_score": norm["away_goals"],
            "neutral_site": "unknown",
            "match_stage": "unknown",
            "tournament_round": "unknown",
            "country_or_team_type": "national_team",
            "data_source": norm["data_source"],
            "has_event_data": False,
            "has_360_data": False,
            "data_mode": "sparse_free_data_projection",
            "event_style_flags": "missing_event_data|missing_neutral_site",
        })
        for col in INTERNATIONAL_MATCH_COLUMNS:
            if col not in frame:
                frame[col] = pd.NA
        frames.append(frame[INTERNATIONAL_MATCH_COLUMNS])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=INTERNATIONAL_MATCH_COLUMNS)
