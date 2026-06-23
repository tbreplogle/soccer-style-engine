from __future__ import annotations

import json
from pathlib import Path
from typing import Any


INTERNATIONAL_HINTS = [
    "world cup",
    "euro",
    "copa america",
    "afcon",
    "africa cup",
    "nations league",
    "gold cup",
    "women's world cup",
    "womens world cup",
    "international",
]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _looks_international(name: str) -> bool:
    lower = name.lower()
    if "europa league" in lower or "champions league" in lower:
        return False
    return any(hint in lower for hint in INTERNATIONAL_HINTS)


def audit_international_readiness(statsbomb_root: str | Path = "data/raw/statsbomb-open-data/data", output_dir: str | Path = "outputs/reports") -> dict[str, Any]:
    root = Path(statsbomb_root)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    competitions_path = root / "competitions.json"
    available: list[dict[str, Any]] = []
    match_counts: list[dict[str, Any]] = []
    event_data_available = False
    three_sixty_available = False
    setup_note = ""
    if competitions_path.exists():
        competitions = _load_json(competitions_path)
        for comp in competitions:
            name = str(comp.get("competition_name", ""))
            if not _looks_international(name):
                continue
            comp_id = comp.get("competition_id")
            season_id = comp.get("season_id")
            available.append({
                "competition_id": comp_id,
                "season_id": season_id,
                "competition_name": name,
                "season_name": comp.get("season_name", ""),
            })
            matches_path = root / "matches" / str(comp_id) / f"{season_id}.json"
            count = 0
            if matches_path.exists():
                matches = _load_json(matches_path)
                count = len(matches)
                for match in matches:
                    match_id = str(match.get("match_id", ""))
                    if (root / "events" / f"{match_id}.json").exists():
                        event_data_available = True
                    if (root / "three-sixty" / f"{match_id}.json").exists() or (root / "three_sixty" / f"{match_id}.json").exists():
                        three_sixty_available = True
            match_counts.append({
                "competition_id": comp_id,
                "season_id": season_id,
                "competition_name": name,
                "season_name": comp.get("season_name", ""),
                "matches": count,
            })
    else:
        setup_note = f"StatsBomb competitions file was not found at {competitions_path}."
    current_data_available = False
    recommended = (
        "Build a separate international module with sparse-sample priors, neutral-site handling, tournament context, opponent-strength normalization, and roster volatility notes."
    )
    result = {
        "available_international_competitions": available,
        "match_counts": match_counts,
        "event_data_available": event_data_available,
        "three_sixty_available": three_sixty_available,
        "current_data_available": current_data_available,
        "recommended_next_international_phase": recommended,
        "setup_note": setup_note,
        "limitations": (
            "International projections require separate logic for sparse matches, neutral sites, roster volatility, tournament effects, and uneven opponent quality. Club and country ratings should not be mixed."
        ),
    }
    report = write_international_readiness_report(result, output / "international_readiness_audit.md")
    result["report"] = report
    result["report_path"] = output / "international_readiness_audit.md"
    return result


def write_international_readiness_report(result: dict[str, Any], output_path: str | Path) -> str:
    lines = [
        "# International Readiness Audit",
        "",
        result.get("setup_note") or "Local StatsBomb competition metadata was inspected.",
        "",
        "## Available International Competitions",
        "",
    ]
    comps = result["available_international_competitions"]
    if not comps:
        lines.append("_No international competitions found locally._")
    else:
        lines.append("| competition | season | matches |")
        lines.append("| --- | --- | --- |")
        counts = {(row["competition_id"], row["season_id"]): row["matches"] for row in result["match_counts"]}
        for comp in comps:
            lines.append(f"| {comp['competition_name']} | {comp['season_name']} | {counts.get((comp['competition_id'], comp['season_id']), 0)} |")
    lines.extend([
        "",
        "## Data Availability",
        "",
        f"Event data available: `{result['event_data_available']}`",
        f"360 data available: `{result['three_sixty_available']}`",
        f"Current live international data available: `{result['current_data_available']}`",
        "",
        "## Recommendation",
        "",
        result["recommended_next_international_phase"],
        "",
        result["limitations"],
        "",
    ])
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report
