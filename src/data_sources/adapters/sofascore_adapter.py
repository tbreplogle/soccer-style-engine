from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_sources.source_result import SourceResult
from src.international_current.current_international_schema import CurrentInternationalFixture, CurrentInternationalMatchStats


SOFASCORE_BASE_URL = "https://www.sofascore.com/api/v1"
DEFAULT_HEADERS = {
    "User-Agent": "soccer-style-engine/0.1 conservative-source-probe",
    "Accept": "application/json",
}


@dataclass
class SofaScoreProbeLog:
    endpoint_name: str
    url: str = ""
    request_attempted: bool = False
    cache_hit: bool = False
    status_code: int | None = None
    item_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _slug(value: str | None) -> str:
    text = str(value or "all").strip().lower()
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text)
    return "_".join(part for part in cleaned.split("_") if part) or "all"


def _cache_path(cache_dir: str | Path, endpoint_name: str, key: str) -> Path:
    return Path(cache_dir) / f"sofascore_{_slug(endpoint_name)}_{_slug(key)}.json"


def read_cached_json(cache_dir: str | Path, endpoint_name: str, key: str) -> tuple[dict[str, Any] | None, Path]:
    path = _cache_path(cache_dir, endpoint_name, key)
    if not path.exists():
        return None, path
    return json.loads(path.read_text(encoding="utf-8")), path


def write_cached_json(cache_dir: str | Path, endpoint_name: str, key: str, payload: dict[str, Any]) -> Path:
    path = _cache_path(cache_dir, endpoint_name, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _request_json(
    url: str,
    *,
    allow_network: bool,
    timeout: float = 8.0,
    retries: int = 1,
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, SofaScoreProbeLog]:
    log = SofaScoreProbeLog(endpoint_name="request", url=url)
    if not allow_network:
        log.warnings.append("Network disabled; request was not attempted.")
        return None, log
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    for attempt in range(max(1, retries + 1)):
        log.request_attempted = True
        request = urllib.request.Request(url, headers=merged_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                log.status_code = int(response.status)
                body = response.read().decode("utf-8")
                return json.loads(body), log
        except urllib.error.HTTPError as exc:
            log.status_code = int(exc.code)
            log.errors.append(f"HTTP {exc.code}: {exc.reason}")
            if exc.code in {401, 403, 429}:
                log.warnings.append("Request blocked or rate-limited; no bypass attempted.")
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            log.errors.append(str(exc))
        if attempt < retries:
            time.sleep(0.5)
    return None, log


def _fetch_json(
    endpoint_name: str,
    key: str,
    url: str,
    *,
    allow_network: bool,
    cache_dir: str | Path,
    timeout: float = 8.0,
    retries: int = 1,
) -> tuple[dict[str, Any] | None, SofaScoreProbeLog]:
    cached, path = read_cached_json(cache_dir, endpoint_name, key)
    if cached is not None:
        return cached, SofaScoreProbeLog(endpoint_name=endpoint_name, url=url, cache_hit=True, warnings=[f"Cache hit: {path}"])
    payload, log = _request_json(url, allow_network=allow_network, timeout=timeout, retries=retries)
    log.endpoint_name = endpoint_name
    if payload is not None:
        write_cached_json(cache_dir, endpoint_name, key, payload)
        log.warnings.append(f"Cached response: {path}")
    else:
        log.warnings.append(f"Cache miss: {path}")
    return payload, log


def _nested(row: dict[str, Any], *keys: str) -> Any:
    value: Any = row
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _status(row: dict[str, Any]) -> str:
    text = str(_nested(row, "status", "type") or _nested(row, "status", "description") or "").lower()
    if text in {"notstarted", "scheduled", "not started"}:
        return "scheduled"
    if text in {"inprogress", "live"}:
        return "live"
    if text in {"finished", "ended", "complete"}:
        return "complete"
    if "postpon" in text:
        return "postponed"
    return text or "unknown"


def _score(row: dict[str, Any], side: str) -> float | None:
    value = _nested(row, f"{side}Score", "current")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_date(row: dict[str, Any]) -> tuple[str, str]:
    timestamp = row.get("startTimestamp")
    if not timestamp:
        return str(row.get("date") or ""), str(row.get("time") or "")
    dt = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
    return dt.date().isoformat(), dt.time().replace(microsecond=0).isoformat()


def parse_fixtures(payload: dict[str, Any], competition: str = "", team: str = "") -> list[CurrentInternationalFixture]:
    events = payload.get("events") or payload.get("matches") or []
    fixtures: list[CurrentInternationalFixture] = []
    competition_filter = competition.lower().strip()
    team_filter = team.lower().strip()
    for event in events:
        if not isinstance(event, dict):
            continue
        tournament = _nested(event, "tournament", "name") or _nested(event, "uniqueTournament", "name") or ""
        category = _nested(event, "tournament", "category", "name") or ""
        competition_text = " ".join(str(x) for x in [tournament, category] if x)
        home = str(_nested(event, "homeTeam", "name") or event.get("home_team") or "")
        away = str(_nested(event, "awayTeam", "name") or event.get("away_team") or "")
        if competition_filter and competition_filter not in competition_text.lower():
            continue
        if team_filter and team_filter not in home.lower() and team_filter not in away.lower():
            continue
        match_date, kickoff_time = _event_date(event)
        fixtures.append(CurrentInternationalFixture(
            source_name="sofascore",
            source_match_id=str(event.get("id") or event.get("source_match_id") or ""),
            competition=str(tournament or competition or "unknown"),
            season=str(_nested(event, "season", "name") or _nested(event, "season", "year") or ""),
            match_date=match_date,
            kickoff_time=kickoff_time,
            home_team=home,
            away_team=away,
            neutral_site="unknown",
            venue=str(_nested(event, "venue", "stadium", "name") or _nested(event, "venue", "name") or ""),
            status=_status(event),
            home_score=_score(event, "home"),
            away_score=_score(event, "away"),
            round_name=str(_nested(event, "roundInfo", "name") or _nested(event, "roundInfo", "round") or ""),
            group_name=str(_nested(event, "tournament", "category", "name") or ""),
            source_url=f"https://www.sofascore.com/event/{event.get('id')}" if event.get("id") else "",
            reliability_status="sofascore_cached_or_live_probe",
            warnings=["SofaScore fixture probe result; not true tracking data."],
        ))
    return fixtures


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _assign_stat(stats: dict[str, float | None], name: str, home: Any, away: Any) -> None:
    label = name.lower()
    mapping = [
        (("possession", "ball possession"), "possession"),
        (("shots on target",), "shots_on_target"),
        (("total shots", "shots"), "shots"),
        (("corner",), "corners"),
        (("foul",), "fouls"),
        (("yellow card", "red card", "cards"), "cards"),
        (("expected goals on target", "xgot", "xg on target"), "xgot"),
        (("expected goals", "xg"), "xg"),
    ]
    for needles, field in mapping:
        if any(needle in label for needle in needles):
            stats[f"{field}_home"] = _numeric(home)
            stats[f"{field}_away"] = _numeric(away)
            return


def parse_match_statistics(
    payload: dict[str, Any],
    *,
    match_id: str = "",
    home_team: str = "",
    away_team: str = "",
) -> CurrentInternationalMatchStats | None:
    containers = payload.get("statistics") or payload.get("groups") or []
    stats: dict[str, float | None] = {}
    for period in containers:
        groups = period.get("groups", []) if isinstance(period, dict) else []
        if "statisticsItems" in period:
            groups = [period]
        for group in groups:
            for item in group.get("statisticsItems", []) if isinstance(group, dict) else []:
                name = str(item.get("name") or item.get("key") or "")
                home = item.get("homeValue", item.get("home"))
                away = item.get("awayValue", item.get("away"))
                _assign_stat(stats, name, home, away)
    if not stats:
        return None
    has_xg = stats.get("xg_home") is not None or stats.get("xg_away") is not None
    return CurrentInternationalMatchStats(
        source_name="sofascore",
        source_match_id=match_id,
        home_team=home_team,
        away_team=away_team,
        possession_home=stats.get("possession_home"),
        possession_away=stats.get("possession_away"),
        shots_home=stats.get("shots_home"),
        shots_away=stats.get("shots_away"),
        shots_on_target_home=stats.get("shots_on_target_home"),
        shots_on_target_away=stats.get("shots_on_target_away"),
        xg_home=stats.get("xg_home"),
        xg_away=stats.get("xg_away"),
        xgot_home=stats.get("xgot_home"),
        xgot_away=stats.get("xgot_away"),
        corners_home=stats.get("corners_home"),
        corners_away=stats.get("corners_away"),
        fouls_home=stats.get("fouls_home"),
        fouls_away=stats.get("fouls_away"),
        cards_home=stats.get("cards_home"),
        cards_away=stats.get("cards_away"),
        data_mode="current_fixture_xg" if has_xg else "current_fixture_stats",
        reliability_status="sofascore_cached_or_live_probe",
        warnings=["SofaScore match-stat probe result; missing fields remain null."],
    )


def parse_lineup_availability(payload: dict[str, Any]) -> tuple[bool, bool]:
    home_players = _nested(payload, "home", "players") or []
    away_players = _nested(payload, "away", "players") or []
    lineups_available = bool(home_players or away_players or payload.get("confirmed"))
    player_ratings_available = False
    for player in [*home_players, *away_players]:
        if not isinstance(player, dict):
            continue
        stats = player.get("statistics") or {}
        if player.get("rating") is not None or stats.get("rating") is not None:
            player_ratings_available = True
            break
    return lineups_available, player_ratings_available


def fetch_fixtures_by_date(
    as_of_date: str,
    *,
    competition: str = "",
    team: str = "",
    allow_network: bool = False,
    cache_dir: str | Path = "data/source_cache/sofascore",
) -> tuple[list[CurrentInternationalFixture], SofaScoreProbeLog]:
    encoded_date = urllib.parse.quote(as_of_date)
    url = f"{SOFASCORE_BASE_URL}/sport/football/scheduled-events/{encoded_date}"
    payload, log = _fetch_json("fixtures", f"{as_of_date}_{competition}_{team}", url, allow_network=allow_network, cache_dir=cache_dir)
    fixtures = parse_fixtures(payload or {}, competition=competition, team=team)
    log.item_count = len(fixtures)
    if payload is None:
        log.warnings.append("No SofaScore fixture payload available.")
    return fixtures, log


def fetch_match_statistics(
    match_id: str,
    *,
    home_team: str = "",
    away_team: str = "",
    allow_network: bool = False,
    cache_dir: str | Path = "data/source_cache/sofascore",
) -> tuple[CurrentInternationalMatchStats | None, SofaScoreProbeLog]:
    url = f"{SOFASCORE_BASE_URL}/event/{urllib.parse.quote(str(match_id))}/statistics"
    payload, log = _fetch_json("match_statistics", str(match_id), url, allow_network=allow_network, cache_dir=cache_dir)
    stats = parse_match_statistics(payload or {}, match_id=str(match_id), home_team=home_team, away_team=away_team)
    log.item_count = 1 if stats else 0
    if payload is None:
        log.warnings.append("No SofaScore match-stat payload available.")
    if stats is None:
        log.warnings.append("No match statistics parsed.")
    return stats, log


def fetch_lineups(
    match_id: str,
    *,
    allow_network: bool = False,
    cache_dir: str | Path = "data/source_cache/sofascore",
) -> tuple[bool, bool, SofaScoreProbeLog]:
    url = f"{SOFASCORE_BASE_URL}/event/{urllib.parse.quote(str(match_id))}/lineups"
    payload, log = _fetch_json("lineups", str(match_id), url, allow_network=allow_network, cache_dir=cache_dir)
    lineups, ratings = parse_lineup_availability(payload or {})
    log.item_count = int(lineups)
    if payload is None:
        log.warnings.append("No SofaScore lineup payload available.")
    return lineups, ratings, log


def fetch_match_details(
    match_id: str,
    *,
    allow_network: bool = False,
    cache_dir: str | Path = "data/source_cache/sofascore",
) -> tuple[dict[str, Any] | None, SofaScoreProbeLog]:
    url = f"{SOFASCORE_BASE_URL}/event/{urllib.parse.quote(str(match_id))}"
    return _fetch_json("match_details", str(match_id), url, allow_network=allow_network, cache_dir=cache_dir)


def fetch_player_ratings(
    match_id: str,
    *,
    allow_network: bool = False,
    cache_dir: str | Path = "data/source_cache/sofascore",
) -> tuple[bool, SofaScoreProbeLog]:
    lineups, ratings, log = fetch_lineups(match_id, allow_network=allow_network, cache_dir=cache_dir)
    if not lineups:
        log.warnings.append("Player ratings cannot be assessed because lineups were unavailable.")
    return ratings, log


def _stats_frame(stats: list[CurrentInternationalMatchStats]) -> pd.DataFrame:
    columns = [item.name for item in fields(CurrentInternationalMatchStats)]
    return pd.DataFrame([item.to_dict() for item in stats], columns=columns)


def _fixtures_frame(fixtures: list[CurrentInternationalFixture]) -> pd.DataFrame:
    columns = [item.name for item in fields(CurrentInternationalFixture)]
    return pd.DataFrame([item.to_dict() for item in fixtures], columns=columns)


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["No rows."]
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in frame.iterrows():
        values = [str(row.get(col, "")).replace("|", "\\|").replace("\n", " ") for col in columns]
        lines.append("| " + " | ".join(values) + " |")
    return lines


def _write_probe_summary(path: Path, manifest: dict[str, Any], logs: list[SofaScoreProbeLog]) -> Path:
    lines = [
        "# SofaScore Current Data Probe",
        "",
        f"Generated at: {manifest['generated_at']}",
        f"As-of date: `{manifest['as_of_date']}`",
        f"Network allowed: `{manifest['allow_network']}`",
        "",
        "## Guardrails",
        "",
        "- No current StatsBomb data is used.",
        "- No Selenium, login, CAPTCHA, anti-bot, or paywall bypass is used.",
        "- Missing SofaScore fields remain null.",
        "- SofaScore data is not treated as true tracking data.",
        "- No betting recommendations are produced.",
        "",
        "## Availability",
        "",
        f"- Fixtures found: {manifest['fixture_count']}",
        f"- Match stats found: {manifest['match_stats_count']}",
        f"- xG found: {manifest['xg_found']}",
        f"- xGOT found: {manifest['xgot_found']}",
        f"- Lineups found: {manifest['lineups_found']}",
        f"- Player ratings found: {manifest['player_ratings_found']}",
        "",
        "## Probe Logs",
        "",
    ]
    log_frame = pd.DataFrame([log.to_dict() for log in logs])
    for column in ["warnings", "errors"]:
        if column in log_frame:
            log_frame[column] = log_frame[column].apply(lambda values: "; ".join(values or []))
    lines.extend(_markdown_table(log_frame))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def probe_sofascore(
    *,
    as_of_date: str,
    competition: str = "",
    match_id: str | None = None,
    team: str = "",
    allow_network: bool = False,
    cache_dir: str | Path = "data/source_cache/sofascore",
    output_dir: str | Path = "outputs/source_probes/sofascore",
    max_matches: int = 5,
) -> dict[str, Any]:
    logs: list[SofaScoreProbeLog] = []
    fixtures, fixture_log = fetch_fixtures_by_date(
        as_of_date,
        competition=competition,
        team=team,
        allow_network=allow_network,
        cache_dir=cache_dir,
    )
    logs.append(fixture_log)
    selected_ids = [str(match_id)] if match_id else [fixture.source_match_id for fixture in fixtures if fixture.source_match_id][:max_matches]
    fixture_by_id = {fixture.source_match_id: fixture for fixture in fixtures}
    stats_rows: list[CurrentInternationalMatchStats] = []
    lineups_found = False
    ratings_found = False
    for selected_id in selected_ids:
        fixture = fixture_by_id.get(str(selected_id))
        stats, stats_log = fetch_match_statistics(
            selected_id,
            home_team=fixture.home_team if fixture else "",
            away_team=fixture.away_team if fixture else "",
            allow_network=allow_network,
            cache_dir=cache_dir,
        )
        logs.append(stats_log)
        lineups, ratings, lineup_log = fetch_lineups(selected_id, allow_network=allow_network, cache_dir=cache_dir)
        logs.append(lineup_log)
        lineups_found = lineups_found or lineups
        ratings_found = ratings_found or ratings
        if stats:
            stats.lineups_available = lineups
            stats.player_ratings_available = ratings
            stats_rows.append(stats)
    run_dir = Path(output_dir) / as_of_date
    run_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = run_dir / "sofascore_fixture_probe.csv"
    stats_path = run_dir / "sofascore_match_stats_probe.csv"
    _fixtures_frame(fixtures).to_csv(fixture_path, index=False)
    _stats_frame(stats_rows).to_csv(stats_path, index=False)
    date_values = [fixture.match_date for fixture in fixtures if fixture.match_date]
    competitions = sorted({fixture.competition for fixture in fixtures if fixture.competition})
    xg_found = any(stat.xg_home is not None or stat.xg_away is not None for stat in stats_rows)
    xgot_found = any(stat.xgot_home is not None or stat.xgot_away is not None for stat in stats_rows)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_name": "sofascore",
        "as_of_date": as_of_date,
        "competition": competition,
        "team": team,
        "match_id": match_id or "",
        "allow_network": allow_network,
        "cache_dir": str(cache_dir),
        "fixture_count": len(fixtures),
        "match_stats_count": len(stats_rows),
        "xg_found": xg_found,
        "xgot_found": xgot_found,
        "lineups_found": lineups_found,
        "player_ratings_found": ratings_found,
        "date_min": min(date_values, default=""),
        "date_max": max(date_values, default=""),
        "competitions_found": competitions,
        "probe_logs": [log.to_dict() for log in logs],
        "output_paths": {
            "summary": str(run_dir / "sofascore_probe_summary.md"),
            "fixtures": str(fixture_path),
            "match_stats": str(stats_path),
            "manifest": str(run_dir / "sofascore_probe_manifest.json"),
        },
        "guardrails": {
            "current_statsbomb_used": False,
            "no_bypass_attempted": True,
            "no_betting_recommendations": True,
            "not_true_tracking_data": True,
        },
    }
    manifest_path = run_dir / "sofascore_probe_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    summary_path = _write_probe_summary(run_dir / "sofascore_probe_summary.md", manifest, logs)
    result_status = "success" if fixtures or stats_rows else ("warn" if allow_network else "skipped")
    source_result = SourceResult(
        source_name="sofascore",
        status=result_status,
        rows_returned=len(fixtures) + len(stats_rows),
        fields_available=[
            field for field, present in {
                "fixtures": bool(fixtures),
                "scores": any(f.home_score is not None or f.away_score is not None for f in fixtures),
                "match_stats": bool(stats_rows),
                "xg": xg_found,
                "xgot": xgot_found,
                "lineups": lineups_found,
                "player_ratings": ratings_found,
            }.items()
            if present
        ],
        fields_missing=[
            field for field, present in {
                "fixtures": bool(fixtures),
                "match_stats": bool(stats_rows),
                "xg": xg_found,
                "xgot": xgot_found,
                "lineups": lineups_found,
                "player_ratings": ratings_found,
            }.items()
            if not present
        ],
        competitions_found=competitions,
        date_min=manifest["date_min"],
        date_max=manifest["date_max"],
        currentness_status="live_or_cached_probe" if allow_network else "local_cache_probe_only",
        coverage_status="fixture_stats_probe" if stats_rows else ("fixture_probe" if fixtures else "no_sofascore_data_available"),
        reliability_status="safe_probe_with_cache",
        cache_path=str(cache_dir),
        data_mode="current_fixture_xg" if xg_found else ("current_fixture_stats" if stats_rows else ("current_fixture_result" if fixtures else "unavailable")),
        warnings=[
            "SofaScore probe is conservative and does not bypass blocks.",
            "Missing fields remain null; SofaScore is not treated as true tracking data.",
            *[warning for log in logs for warning in log.warnings],
        ],
        errors=[error for log in logs for error in log.errors],
    )
    return {
        "source_result": source_result,
        "fixtures": fixtures,
        "match_stats": stats_rows,
        "logs": logs,
        "summary_path": summary_path,
        "fixture_path": fixture_path,
        "match_stats_path": stats_path,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }


def audit_sofascore(allow_network: bool = False):
    result = SourceResult(
        source_name="sofascore",
        status="warn" if allow_network else "skipped",
        fields_missing=["fixtures", "match_stats", "xg", "lineups", "player_ratings"],
        currentness_status="network_probe_available" if allow_network else "not_checked_no_network",
        coverage_status="use_probe_sofascore_for_details",
        reliability_status="planned_safe_probe",
        warnings=["Run probe-sofascore for a conservative current-data check; no Selenium or anti-bot bypass is used."],
        data_mode="unavailable",
    )
    return result


def audit_sofascore_current_international(
    allow_network: bool = False,
    as_of_date: str | None = None,
    competition: str = "FIFA World Cup",
    cache_dir: str | Path = "data/source_cache/sofascore",
    output_dir: str | Path = "outputs/source_probes/sofascore",
    max_matches: int = 5,
):
    if not as_of_date:
        result = audit_sofascore(allow_network=allow_network)
        result.warnings.append("No as-of date supplied, so the detailed SofaScore probe was not run.")
        return result, [], []
    probe = probe_sofascore(
        as_of_date=as_of_date,
        competition=competition,
        allow_network=allow_network,
        cache_dir=cache_dir,
        output_dir=output_dir,
        max_matches=max_matches,
    )
    return probe["source_result"], probe["fixtures"], probe["match_stats"]


__all__ = [
    "CurrentInternationalFixture",
    "CurrentInternationalMatchStats",
    "SofaScoreProbeLog",
    "audit_sofascore",
    "audit_sofascore_current_international",
    "fetch_fixtures_by_date",
    "fetch_lineups",
    "fetch_match_details",
    "fetch_match_statistics",
    "fetch_player_ratings",
    "parse_fixtures",
    "parse_lineup_availability",
    "parse_match_statistics",
    "probe_sofascore",
    "read_cached_json",
    "write_cached_json",
]
