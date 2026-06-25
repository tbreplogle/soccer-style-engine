from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.international_current.current_international_schema import CurrentInternationalFixture, CurrentInternationalTeamRating


PLACEHOLDER_SKIP_WARNING = "Unresolved placeholder fixtures were skipped and not projected."


@dataclass(frozen=True)
class FixtureResolution:
    fixture_resolution_status: str
    is_resolved_fixture: bool
    home_team_resolved: bool
    away_team_resolved: bool
    placeholder_reason: str
    projection_eligible: bool
    projection_skip_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_EXACT_PLACEHOLDERS = {
    "tbd",
    "tbc",
    "to be determined",
    "to be confirmed",
    "winner",
    "loser",
    "runner up",
    "runner-up",
}

_PLACEHOLDER_PATTERNS = [
    (re.compile(r"^w\d{1,4}$"), "bracket winner code"),
    (re.compile(r"^l\d{1,4}$"), "bracket loser code"),
    (re.compile(r"^(?:winner|loser)\s+(?:match\s*)?\d{1,4}$"), "bracket match placeholder"),
    (re.compile(r"^(?:runner[- ]?up|second)\s+(?:of\s+)?group\s+[a-z0-9]+$"), "group runner-up placeholder"),
    (re.compile(r"^(?:winner|first|1st)\s+(?:of\s+)?group\s+[a-z0-9]+$"), "group winner placeholder"),
    (re.compile(r"^group\s+[a-z0-9]+\s+(?:winner|runner[- ]?up)$"), "group placement placeholder"),
    (re.compile(r"^[123]\s*[a-l]$"), "group placement code"),
    (re.compile(r"^[123]\s*[a-l](?:\s*/\s*[a-l]){1,8}$"), "multi-group placement code"),
    (re.compile(r"^(?:best\s+)?third[- ]?place\s+team(?:\s+from\s+groups?)?.*$"), "third-place placeholder"),
]


def _norm(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def placeholder_reason(team_name: object) -> str:
    text = _norm(team_name)
    if not text:
        return "empty team name"
    if text in _EXACT_PLACEHOLDERS:
        return "TBD/TBC placeholder"
    for pattern, reason in _PLACEHOLDER_PATTERNS:
        if pattern.fullmatch(text):
            return reason
    if "winner" in text and "group" in text:
        return "group winner placeholder"
    if "runner" in text and "group" in text:
        return "group runner-up placeholder"
    return ""


def is_placeholder_team(team_name: object) -> bool:
    return bool(placeholder_reason(team_name))


def classify_fixture(fixture: CurrentInternationalFixture, *, allow_sample_data: bool = False) -> FixtureResolution:
    home_reason = placeholder_reason(fixture.home_team)
    away_reason = placeholder_reason(fixture.away_team)
    home_resolved = not home_reason
    away_resolved = not away_reason
    is_manual = fixture.source_tier == "manual" or fixture.reliability_status == "manual_fallback" or fixture.source_name == "manual_current_fixture"
    is_sample = bool(fixture.is_sample_data or fixture.source_tier == "sample")
    is_resolved = home_resolved and away_resolved

    if is_sample:
        status = "sample"
    elif is_manual:
        status = "manual"
    elif not is_resolved:
        status = "unresolved_placeholder"
    elif not fixture.home_team or not fixture.away_team:
        status = "invalid"
    else:
        status = "resolved"

    reasons = [reason for reason in [home_reason, away_reason] if reason]
    placeholder = " | ".join(dict.fromkeys(reasons))

    projection_eligible = is_resolved and (not is_sample or allow_sample_data) and status != "invalid"
    if projection_eligible:
        skip_reason = ""
    elif is_sample and not allow_sample_data:
        skip_reason = "sample_requires_allow_sample_data"
    elif status == "unresolved_placeholder":
        skip_reason = f"unresolved_placeholder: {placeholder or 'placeholder team name'}"
    elif status == "invalid":
        skip_reason = "invalid_fixture"
    else:
        skip_reason = "not_projection_eligible"

    return FixtureResolution(
        fixture_resolution_status=status,
        is_resolved_fixture=is_resolved,
        home_team_resolved=home_resolved,
        away_team_resolved=away_resolved,
        placeholder_reason=placeholder,
        projection_eligible=projection_eligible,
        projection_skip_reason=skip_reason,
    )


def rating_status_for_fixture(fixture: CurrentInternationalFixture, ratings: dict[str, CurrentInternationalTeamRating]) -> str:
    home = ratings.get(fixture.home_team)
    away = ratings.get(fixture.away_team)
    home_ok = bool(home and home.rating_value is not None)
    away_ok = bool(away and away.rating_value is not None)
    if home_ok and away_ok:
        return "both_ratings_available"
    if home_ok:
        return "away_rating_missing"
    if away_ok:
        return "home_rating_missing"
    return "both_ratings_missing"


def fixture_readiness_frame(
    fixtures: list[CurrentInternationalFixture],
    ratings: dict[str, CurrentInternationalTeamRating],
    *,
    allow_sample_data: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        resolution = classify_fixture(fixture, allow_sample_data=allow_sample_data)
        rows.append({
            "match_date": fixture.match_date,
            "kickoff_time": fixture.kickoff_time,
            "competition": fixture.competition,
            "round_name": fixture.round_name,
            "group_name": fixture.group_name,
            "home_team": fixture.home_team,
            "away_team": fixture.away_team,
            "neutral_site": fixture.neutral_site,
            "source_name": fixture.source_name,
            "source_tier": fixture.source_tier,
            "reliability_status": fixture.reliability_status,
            "is_sample_data": fixture.is_sample_data,
            "fixture_source_status": fixture.status,
            "rating_status": rating_status_for_fixture(fixture, ratings) if resolution.is_resolved_fixture else "not_applicable_unresolved_fixture",
            "home_rating_available": bool(ratings.get(fixture.home_team) and ratings[fixture.home_team].rating_value is not None),
            "away_rating_available": bool(ratings.get(fixture.away_team) and ratings[fixture.away_team].rating_value is not None),
            "warnings": " | ".join(w for w in fixture.warnings if w),
            **resolution.to_dict(),
        })
    return pd.DataFrame(rows)


def readiness_summary(readiness: pd.DataFrame) -> dict[str, Any]:
    if readiness.empty:
        return {
            "total_harvested_fixtures": 0,
            "resolved_fixtures": 0,
            "unresolved_placeholders": 0,
            "projection_eligible_fixtures": 0,
            "skipped_fixtures": 0,
            "skipped_placeholder_rows": 0,
            "rating_coverage_projected": 0.0,
            "teams_missing_ratings_eligible": [],
            "strict_readiness_status": "fail",
        }
    eligible = readiness[readiness["projection_eligible"].astype(bool)]
    unresolved = readiness[readiness["fixture_resolution_status"] == "unresolved_placeholder"]
    missing_rating_rows = eligible[eligible["rating_status"] != "both_ratings_available"]
    missing: list[str] = []
    for _, row in missing_rating_rows.iterrows():
        if not bool(row.get("home_rating_available")):
            missing.append(str(row.get("home_team", "")))
        if not bool(row.get("away_rating_available")):
            missing.append(str(row.get("away_team", "")))
    coverage = 0.0 if eligible.empty else round(float((eligible["rating_status"] == "both_ratings_available").mean()), 4)
    strict_status = "pass"
    if eligible.empty or missing:
        strict_status = "fail"
    elif not unresolved.empty:
        strict_status = "warning"
    return {
        "total_harvested_fixtures": int(len(readiness)),
        "resolved_fixtures": int(readiness["is_resolved_fixture"].astype(bool).sum()),
        "unresolved_placeholders": int(len(unresolved)),
        "projection_eligible_fixtures": int(len(eligible)),
        "skipped_fixtures": int((~readiness["projection_eligible"].astype(bool)).sum()),
        "skipped_placeholder_rows": int(len(unresolved)),
        "rating_coverage_projected": coverage,
        "teams_missing_ratings_eligible": sorted(set(team for team in missing if team)),
        "strict_readiness_status": strict_status,
    }


def write_fixture_readiness_outputs(
    *,
    run_dir: str | Path,
    fixtures: list[CurrentInternationalFixture],
    ratings: dict[str, CurrentInternationalTeamRating],
    allow_sample_data: bool = False,
) -> dict[str, Any]:
    readiness = fixture_readiness_frame(fixtures, ratings, allow_sample_data=allow_sample_data)
    summary = readiness_summary(readiness)
    output = Path(run_dir) / "fixture_readiness"
    output.mkdir(parents=True, exist_ok=True)

    resolved = readiness[readiness["is_resolved_fixture"].astype(bool)] if not readiness.empty else readiness
    unresolved = readiness[readiness["fixture_resolution_status"] == "unresolved_placeholder"] if not readiness.empty else readiness
    eligible = readiness[readiness["projection_eligible"].astype(bool)] if not readiness.empty else readiness
    skipped = readiness[~readiness["projection_eligible"].astype(bool)] if not readiness.empty else readiness

    paths = {
        "fixture_readiness_summary": output / "fixture_readiness_summary.md",
        "resolved_fixtures": output / "resolved_fixtures.csv",
        "unresolved_fixtures": output / "unresolved_fixtures.csv",
        "projection_eligible_fixtures": output / "projection_eligible_fixtures.csv",
        "projection_skipped_fixtures": output / "projection_skipped_fixtures.csv",
    }
    resolved.to_csv(paths["resolved_fixtures"], index=False)
    unresolved.to_csv(paths["unresolved_fixtures"], index=False)
    eligible.to_csv(paths["projection_eligible_fixtures"], index=False)
    skipped.to_csv(paths["projection_skipped_fixtures"], index=False)

    examples = unresolved[["home_team", "away_team", "placeholder_reason"]].head(10).to_dict("records") if not unresolved.empty else []
    lines = [
        "# Fixture Readiness",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Counts",
        "",
        f"- Total harvested fixtures: {summary['total_harvested_fixtures']}",
        f"- Resolved fixtures: {summary['resolved_fixtures']}",
        f"- Unresolved placeholders: {summary['unresolved_placeholders']}",
        f"- Projection eligible fixtures: {summary['projection_eligible_fixtures']}",
        f"- Skipped fixtures: {summary['skipped_fixtures']}",
        f"- Rating coverage for projection eligible fixtures: {summary['rating_coverage_projected']}",
        f"- Teams missing ratings among eligible fixtures: {', '.join(summary['teams_missing_ratings_eligible']) or 'none'}",
        f"- Strict readiness status for eligible fixtures: `{summary['strict_readiness_status']}`",
        "",
        "## Guardrails",
        "",
        "- Unresolved placeholder fixtures are not projected by default.",
        "- Placeholder teams do not receive fake ratings.",
        "- Current StatsBomb is not used.",
        "- Proxy score adjustments remain disabled.",
        "- Output is projection review context, not betting guidance.",
        "",
        "## Skipped Placeholder Examples",
        "",
    ]
    if examples:
        for item in examples:
            lines.append(f"- {item['home_team']} vs {item['away_team']}: {item['placeholder_reason']}")
    else:
        lines.append("- none")
    paths["fixture_readiness_summary"].write_text("\n".join(lines), encoding="utf-8")
    return {
        "frame": readiness,
        "summary": summary,
        "paths": {key: str(value) for key, value in paths.items()},
    }
