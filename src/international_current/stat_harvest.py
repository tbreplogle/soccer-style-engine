from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.international_current.fixture_harvest import SourceAuditRow
from src.international_current.team_name_normalization import normalize_team_name


STAT_COLUMNS = [
    "team_name",
    "normalized_team_name",
    "goals_for_per_match",
    "goals_against_per_match",
    "xg_for_per_match",
    "xg_against_per_match",
    "shots_for_per_match",
    "shots_against_per_match",
    "shots_on_target_for_per_match",
    "shots_on_target_against_per_match",
    "clean_sheet_rate",
    "failed_to_score_rate",
    "cards_per_match",
    "red_cards_per_match",
    "source_name",
    "source_status",
    "warning",
]


def _num(value: object) -> float | None:
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _stat_frame_from_cache(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw = row.get("team_name") or row.get("team") or ""
            normalized = normalize_team_name(raw)
            rows.append({
                "team_name": raw,
                "normalized_team_name": normalized.normalized_name,
                "goals_for_per_match": _num(row.get("goals_for_per_match")),
                "goals_against_per_match": _num(row.get("goals_against_per_match")),
                "xg_for_per_match": _num(row.get("xg_for_per_match")),
                "xg_against_per_match": _num(row.get("xg_against_per_match")),
                "shots_for_per_match": _num(row.get("shots_for_per_match")),
                "shots_against_per_match": _num(row.get("shots_against_per_match")),
                "shots_on_target_for_per_match": _num(row.get("shots_on_target_for_per_match")),
                "shots_on_target_against_per_match": _num(row.get("shots_on_target_against_per_match")),
                "clean_sheet_rate": _num(row.get("clean_sheet_rate")),
                "failed_to_score_rate": _num(row.get("failed_to_score_rate")),
                "cards_per_match": _num(row.get("cards_per_match")),
                "red_cards_per_match": _num(row.get("red_cards_per_match")),
                "source_name": row.get("source_name") or "local_current_international_stat_cache",
                "source_status": row.get("source_status") or "local_cache",
                "warning": " | ".join(w for w in [normalized.warning, row.get("warning") or ""] if w),
            })
    frame = pd.DataFrame(rows)
    for column in STAT_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[STAT_COLUMNS]


def harvest_current_international_stats(
    *,
    fixture_teams: list[str] | None = None,
    allow_network: bool = False,
    cache_dir: str | Path = "data/source_cache/current_international",
) -> dict[str, Any]:
    cache = Path(cache_dir)
    path = cache / "stats.csv"
    audit_rows: list[SourceAuditRow] = []
    if path.exists():
        try:
            frame = _stat_frame_from_cache(path)
            teams = {normalize_team_name(team).normalized_name for team in fixture_teams or []}
            coverage = int(frame["normalized_team_name"].isin(teams).sum()) if teams else len(frame)
            audit_rows.append(SourceAuditRow(
                source_name="local_current_international_stat_cache",
                source_type="stat",
                attempted=True,
                success=True,
                row_count=len(frame),
                coverage_count=coverage,
                cache_path=str(path),
                freshness_date=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date().isoformat(),
                recommendation="Use available basic stats; blank xG/shots fields remain unavailable.",
            ))
            return {"stats_frame": frame, "audit_frame": pd.DataFrame([row.to_dict() for row in audit_rows])}
        except Exception as exc:
            audit_rows.append(SourceAuditRow(
                source_name="local_current_international_stat_cache",
                source_type="stat",
                attempted=True,
                error_message=str(exc),
                cache_path=str(path),
                recommendation="Fix or refresh stat cache.",
            ))
    else:
        audit_rows.append(SourceAuditRow(
            source_name="local_current_international_stat_cache",
            source_type="stat",
            attempted=True,
            skipped=True,
            cache_path=str(path),
            recommendation="No local basic stat cache available; leave xG/shots blank.",
        ))

    for source_name in ["fbref_world_cup_team_tables", "espn_boxscore_pages", "whoscored_public_probe", "markstats_public_probe", "scoreroom_public_probe", "transfermarkt_public_probe"]:
        audit_rows.append(SourceAuditRow(
            source_name=source_name,
            source_type="stat",
            attempted=allow_network,
            skipped=not allow_network,
            recommendation="Network parser not enabled; keep as optional source ladder candidate.",
        ))
    frame = pd.DataFrame(columns=STAT_COLUMNS)
    return {"stats_frame": frame, "audit_frame": pd.DataFrame([row.to_dict() for row in audit_rows])}
