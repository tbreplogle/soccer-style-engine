from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_sources.adapters.openfootball_worldcup_adapter import audit_openfootball_worldcup, parse_openfootball_fixtures
from src.international_current.current_international_schema import CurrentInternationalFixture
from src.international_current.team_name_normalization import normalize_team_pair


FIXTURE_COLUMNS = [
    "match_date",
    "kickoff_time",
    "competition",
    "round_name",
    "group_name",
    "home_team",
    "away_team",
    "neutral_site",
    "venue",
    "source_name",
    "source_url",
    "source_tier",
    "source_status",
    "is_sample_data",
    "reliability_status",
    "fixture_confidence",
    "warnings",
]


@dataclass
class SourceAuditRow:
    source_name: str
    source_type: str
    attempted: bool = False
    success: bool = False
    blocked: bool = False
    skipped: bool = False
    requires_manual: bool = False
    row_count: int = 0
    coverage_count: int = 0
    error_message: str = ""
    cache_path: str = ""
    freshness_date: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_sample_path(path: Path) -> bool:
    lowered = [part.lower() for part in path.parts]
    return "sample" in lowered


def _fixture_from_row(row: dict[str, str], source_name: str, source_path: Path) -> CurrentInternationalFixture:
    home, away, warnings = normalize_team_pair(row.get("home_team") or row.get("team_a") or "", row.get("away_team") or row.get("team_b") or "")
    sample = _is_sample_path(source_path)
    return CurrentInternationalFixture(
        source_name=source_name,
        source_match_id=row.get("source_match_id") or row.get("id") or f"{source_name}-{home}-{away}",
        competition=row.get("competition") or "FIFA World Cup",
        season=row.get("season") or "",
        match_date=row.get("match_date") or row.get("date") or "",
        kickoff_time=row.get("kickoff_time") or row.get("time") or "",
        home_team=home,
        away_team=away,
        neutral_site=row.get("neutral_site") or "unknown",
        venue=row.get("venue") or "",
        status=row.get("status") or "scheduled",
        round_name=row.get("round_name") or row.get("round") or "",
        group_name=row.get("group_name") or row.get("group") or "",
        source_url=row.get("source_url") or "",
        reliability_status="sample_only" if sample else row.get("reliability_status") or "local_cache",
        source_tier="sample" if sample else row.get("source_tier") or "real",
        is_sample_data=sample,
        warnings=list(dict.fromkeys([
            *warnings,
            row.get("warnings") or "",
            "Fixture cache provides schedule data; verify kickoff/source freshness.",
        ])),
    )


def _parse_fixture_cache(path: Path, source_name: str) -> list[CurrentInternationalFixture]:
    if path.suffix.lower() == ".json":
        if "openfootball" in source_name:
            return parse_openfootball_fixtures(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("matches", payload if isinstance(payload, list) else [])
        return [_fixture_from_row({key: str(value) for key, value in row.items()}, source_name, path) for row in rows]
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [_fixture_from_row(row, source_name, path) for row in csv.DictReader(handle)]


def _fixture_frame(fixtures: list[CurrentInternationalFixture]) -> pd.DataFrame:
    rows = []
    for fixture in fixtures:
        confidence = "sample" if fixture.is_sample_data else "high" if fixture.source_tier == "real" else "manual"
        rows.append({
            "match_date": fixture.match_date,
            "kickoff_time": fixture.kickoff_time,
            "competition": fixture.competition,
            "round_name": fixture.round_name,
            "group_name": fixture.group_name,
            "home_team": fixture.home_team,
            "away_team": fixture.away_team,
            "neutral_site": fixture.neutral_site,
            "venue": fixture.venue,
            "source_name": fixture.source_name,
            "source_url": fixture.source_url,
            "source_tier": fixture.source_tier,
            "source_status": fixture.status,
            "is_sample_data": fixture.is_sample_data,
            "reliability_status": fixture.reliability_status,
            "fixture_confidence": confidence,
            "warnings": " | ".join(w for w in fixture.warnings if w),
        })
    frame = pd.DataFrame(rows)
    for column in FIXTURE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[FIXTURE_COLUMNS]


def harvest_current_international_fixtures(
    *,
    as_of_date: str,
    competition: str = "FIFA World Cup",
    allow_network: bool = False,
    cache_dir: str | Path = "data/source_cache/current_international",
    max_matches: int | None = None,
    allow_sample_data: bool = False,
) -> dict[str, Any]:
    cache = Path(cache_dir)
    audit_rows: list[SourceAuditRow] = []
    fixtures: list[CurrentInternationalFixture] = []

    candidates = [
        ("local_current_international_fixture_cache", cache / "fixtures.csv"),
        ("local_current_international_fixture_cache", cache / "fixtures.json"),
    ]
    for source_name, path in candidates:
        if not path.exists():
            audit_rows.append(SourceAuditRow(
                source_name=source_name,
                source_type="fixture",
                attempted=True,
                skipped=True,
                cache_path=str(path),
                recommendation="Create or refresh a local fixture cache.",
            ))
            continue
        if _is_sample_path(path) and not allow_sample_data:
            audit_rows.append(SourceAuditRow(
                source_name=source_name,
                source_type="fixture",
                attempted=True,
                skipped=True,
                cache_path=str(path),
                recommendation="Sample fixture cache rejected by default; use --allow-sample-data only for demos.",
            ))
            continue
        try:
            parsed = _parse_fixture_cache(path, source_name)
            fixtures.extend(parsed)
            audit_rows.append(SourceAuditRow(
                source_name=source_name,
                source_type="fixture",
                attempted=True,
                success=bool(parsed),
                row_count=len(parsed),
                coverage_count=len(parsed),
                cache_path=str(path),
                freshness_date=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date().isoformat(),
                recommendation="Use cached fixture rows and verify source freshness." if parsed else "Cache parsed but no fixture rows were found.",
            ))
        except Exception as exc:
            audit_rows.append(SourceAuditRow(
                source_name=source_name,
                source_type="fixture",
                attempted=True,
                success=False,
                error_message=str(exc),
                cache_path=str(path),
                recommendation="Fix or refresh the fixture cache.",
            ))

    default_cache = Path("data/source_cache/current_international")
    if Path(cache_dir) == default_cache:
        openfootball_result, openfootball_fixtures = audit_openfootball_worldcup(
            allow_network=allow_network,
            use_sample_fallback=allow_sample_data,
        )
        fixtures.extend(openfootball_fixtures)
        audit_rows.append(SourceAuditRow(
            source_name="openfootball_worldcup",
            source_type="fixture",
            attempted=True,
            success=bool(openfootball_fixtures),
            skipped=openfootball_result.status == "skipped",
            row_count=len(openfootball_fixtures),
            coverage_count=len(openfootball_fixtures),
            error_message="; ".join(openfootball_result.errors),
            cache_path=openfootball_result.cache_path,
            freshness_date=openfootball_result.date_max,
            recommendation="Use for fixture backbone only; no stats/xG/style fields." if openfootball_fixtures else "No real OpenFootball cache available.",
        ))
    else:
        audit_rows.append(SourceAuditRow(
            source_name="openfootball_worldcup",
            source_type="fixture",
            attempted=False,
            skipped=True,
            recommendation="Skipped global OpenFootball cache because a custom cache_dir was supplied.",
        ))

    for source_name in ["fbref_world_cup_schedule", "espn_scoreboard_schedule"]:
        audit_rows.append(SourceAuditRow(
            source_name=source_name,
            source_type="fixture",
            attempted=allow_network,
            skipped=not allow_network,
            requires_manual=not allow_network,
            recommendation="Network probe not run." if not allow_network else "Live parser not enabled; keep as source ladder candidate.",
        ))

    seen: set[tuple[str, str, str]] = set()
    deduped: list[CurrentInternationalFixture] = []
    conflicts: list[str] = []
    for fixture in fixtures:
        if competition and fixture.competition and competition.lower() not in fixture.competition.lower():
            continue
        key = (fixture.match_date, fixture.home_team, fixture.away_team)
        if key in seen:
            conflicts.append(f"Duplicate fixture candidate flagged for {fixture.match_date} {fixture.home_team} vs {fixture.away_team}.")
            fixture.warnings.append("Duplicate fixture candidate from multiple sources; verify source agreement.")
        else:
            seen.add(key)
        deduped.append(fixture)
    if max_matches is not None:
        deduped = deduped[:max_matches]

    frame = _fixture_frame(deduped)
    return {
        "fixtures": deduped,
        "fixtures_frame": frame,
        "audit_frame": pd.DataFrame([row.to_dict() for row in audit_rows]),
        "conflicts": conflicts,
    }
