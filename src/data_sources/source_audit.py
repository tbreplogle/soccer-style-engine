from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_sources.adapters.fbref_adapter import audit_fbref
from src.data_sources.adapters.football_data_adapter import audit_football_data
from src.data_sources.adapters.eloratings_adapter import audit_eloratings_current
from src.data_sources.adapters.espn_scoreboard_adapter import audit_espn_scoreboard
from src.data_sources.adapters.openfootball_worldcup_adapter import audit_openfootball_worldcup
from src.data_sources.adapters.planned_adapters import planned_source_probe
from src.data_sources.adapters.ratings_adapters import audit_clubelo, audit_eloratings
from src.data_sources.adapters.soccerdata_adapter import audit_soccerdata
from src.data_sources.adapters.sofascore_adapter import audit_sofascore
from src.data_sources.adapters.thestatsapi_worldcup_adapter import audit_thestatsapi_worldcup
from src.data_sources.adapters.understat_adapter import audit_understat
from src.data_sources.adapters.whoscored_adapter import audit_whoscored
from src.data_sources.coverage_matrix import build_coverage_matrix, recommend_source_stack
from src.data_sources.source_registry import get_source_registry
from src.data_sources.source_result import SourceResult


ADAPTERS = {
    "openfootball_worldcup": lambda allow_network, **kwargs: audit_openfootball_worldcup(allow_network=allow_network)[0],
    "thestatsapi_worldcup": lambda allow_network, **kwargs: audit_thestatsapi_worldcup(allow_network=allow_network)[0],
    "football_data": lambda allow_network, **kwargs: audit_football_data(kwargs.get("football_data_raw_dir", "data/raw/football-data")),
    "soccerdata": lambda allow_network, **kwargs: audit_soccerdata(allow_network=allow_network),
    "sofascore": lambda allow_network, **kwargs: audit_sofascore(allow_network=allow_network),
    "whoscored": lambda allow_network, **kwargs: audit_whoscored(allow_network=allow_network),
    "fbref": lambda allow_network, **kwargs: audit_fbref(allow_network=allow_network),
    "understat": lambda allow_network, **kwargs: audit_understat(allow_network=allow_network),
    "clubelo": lambda allow_network, **kwargs: audit_clubelo(allow_network=allow_network),
    "eloratings": lambda allow_network, **kwargs: audit_eloratings_current(allow_network=allow_network)[0],
    "espn_scoreboard": lambda allow_network, **kwargs: audit_espn_scoreboard(allow_network=allow_network)[0],
    "statsbomb_open_data": lambda allow_network, **kwargs: planned_source_probe("statsbomb_open_data", allow_network=allow_network),
}


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["No rows."]
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(row[col]) for col in columns) + " |")
    return lines


def _result_frame(results: list[SourceResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        data = result.to_dict()
        for key in ["fields_available", "fields_missing", "competitions_found", "warnings", "errors"]:
            data[key] = "; ".join(map(str, data.get(key) or []))
        rows.append(data)
    return pd.DataFrame(rows)


def _write_summary(path: Path, results: list[SourceResult], coverage: pd.DataFrame, allow_network: bool) -> None:
    lines = [
        "# Free Current Source Audit",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Network allowed: `{allow_network}`",
        "",
        "## Guardrails",
        "",
        "- No paid APIs.",
        "- No current StatsBomb.",
        "- No anti-bot, login, CAPTCHA, or paywall bypass.",
        "- No betting recommendations.",
        "- Free/scraped proxy data is not true tracking data.",
        "",
        "## Results",
        "",
    ]
    result_frame = _result_frame(results)[["source_name", "status", "rows_returned", "currentness_status", "coverage_status", "reliability_status", "data_mode"]]
    lines.extend(_markdown_table(result_frame))
    lines.extend(["", "## Coverage Matrix", ""])
    lines.extend(_markdown_table(coverage))
    lines.extend([
        "",
        "## Recommended Source Stacks",
        "",
        f"- Club projection: {', '.join(recommend_source_stack('club_projection'))}",
        f"- World Cup projection: {', '.join(recommend_source_stack('world_cup_projection'))}",
        f"- Style/event proxy: {', '.join(recommend_source_stack('style_event_proxy'))}",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def audit_free_sources(
    allow_network: bool = False,
    source: str | None = None,
    competition: str = "",
    season: str = "",
    as_of_date: str | None = None,
    output_dir: str | Path = "outputs/source_audits",
    football_data_raw_dir: str | Path = "data/raw/football-data",
) -> dict[str, Any]:
    registry = get_source_registry()
    selected = [source] if source else list(registry)
    unknown = [item for item in selected if item not in registry]
    if unknown:
        raise ValueError(f"Unknown source(s): {', '.join(unknown)}")
    run_date = as_of_date or date.today().isoformat()
    audit_id = f"{run_date}_{'network' if allow_network else 'local'}"
    audit_dir = Path(output_dir) / audit_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    results: list[SourceResult] = []
    for name in selected:
        try:
            results.append(ADAPTERS[name](allow_network, football_data_raw_dir=str(football_data_raw_dir)))
        except Exception as exc:
            results.append(SourceResult(
                source_name=name,
                status="fail",
                currentness_status="adapter_error",
                coverage_status="adapter_error",
                reliability_status="fail",
                errors=[str(exc)],
                data_mode="unavailable",
            ))
    result_frame = _result_frame(results)
    coverage = build_coverage_matrix([result.to_dict() for result in results])
    results_path = audit_dir / "source_audit_results.csv"
    coverage_path = audit_dir / "source_coverage_matrix.csv"
    summary_path = audit_dir / "source_audit_summary.md"
    manifest_path = audit_dir / "source_audit_manifest.json"
    result_frame.to_csv(results_path, index=False)
    coverage.to_csv(coverage_path, index=False)
    _write_summary(summary_path, results, coverage, allow_network)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": run_date,
        "audit_id": audit_id,
        "allow_network": allow_network,
        "source_filter": source or "",
        "competition": competition,
        "season": season,
        "sources_audited": selected,
        "result_counts": result_frame["status"].value_counts().to_dict() if not result_frame.empty else {},
        "output_paths": {
            "summary": str(summary_path),
            "results": str(results_path),
            "coverage_matrix": str(coverage_path),
            "manifest": str(manifest_path),
        },
        "guardrails": {
            "no_current_statsbomb": True,
            "no_paid_apis": True,
            "no_betting_recommendations": True,
            "no_anti_bot_bypass": True,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "audit_dir": audit_dir,
        "summary_path": summary_path,
        "results_path": results_path,
        "coverage_matrix_path": coverage_path,
        "manifest_path": manifest_path,
        "results": results,
        "coverage_matrix": coverage,
        "manifest": manifest,
    }
