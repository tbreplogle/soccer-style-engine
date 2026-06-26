from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.international_current.historical_rating_matcher import attach_historical_ratings
from src.international_current.historical_rating_snapshots import load_historical_rating_snapshots, seed_historical_rating_snapshots
from src.international_current.historical_results import load_historical_results, seed_historical_results


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(row.get(col, "")).replace("|", "\\|") for col in columns) + " |")
    return "\n".join(lines)


def seed_international_historical_calibration_data(
    *,
    start_date: str,
    end_date: str,
    allow_network: bool = False,
    seed_ratings: bool = False,
    seed_results: bool = False,
    seed_all: bool = False,
    force_refresh: bool = False,
    max_snapshots: int | None = None,
    max_matches: int | None = None,
    cache_dir: str | Path = "data/source_cache/current_international",
    output_dir: str | Path = "outputs/calibration",
) -> dict[str, Any]:
    run_date = date.today().isoformat()
    run_dir = Path(output_dir) / run_date / "historical_seed"
    run_dir.mkdir(parents=True, exist_ok=True)
    do_ratings = seed_all or seed_ratings
    do_results = seed_all or seed_results
    ratings_result = seed_historical_rating_snapshots(
        start_date=start_date,
        end_date=end_date,
        allow_network=allow_network,
        force_refresh=force_refresh,
        max_snapshots=max_snapshots,
        cache_dir=cache_dir,
    ) if do_ratings else {"snapshots": load_historical_rating_snapshots(cache_dir), "fetches": [], "source_status_counts": {"parsed_cache_hit": len(load_historical_rating_snapshots(cache_dir))}}
    results_result = seed_historical_results(
        start_date=start_date,
        end_date=end_date,
        allow_network=allow_network,
        force_refresh=force_refresh,
        max_matches=max_matches,
        cache_dir=cache_dir,
    ) if do_results else {"results": load_historical_results(cache_dir), "fetches": [], "source_status_counts": {"parsed_cache_hit": len(load_historical_results(cache_dir))}}

    snapshots = ratings_result["snapshots"]
    results = results_result["results"]
    matched = attach_historical_ratings(results, snapshots)
    paths = {
        "summary": run_dir / "historical_seed_summary.md",
        "historical_rating_snapshots": run_dir / "historical_rating_snapshots.csv",
        "historical_results": run_dir / "historical_results.csv",
        "historical_matches_with_ratings": run_dir / "historical_matches_with_ratings.csv",
        "manifest": run_dir / "historical_seed_manifest.json",
    }
    snapshots.to_csv(paths["historical_rating_snapshots"], index=False)
    results.to_csv(paths["historical_results"], index=False)
    matched.to_csv(paths["historical_matches_with_ratings"], index=False)
    manifest = {
        "run_id": f"historical_seed_{run_date}",
        "run_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "allow_network": allow_network,
        "historical_rating_snapshot_rows": int(len(snapshots)),
        "historical_results_rows": int(len(results)),
        "historical_matches_with_ratings_rows": int((matched.get("rating_match_status", pd.Series(dtype=str)) == "both_ratings_matched").sum()) if not matched.empty else 0,
        "rating_source_status_counts": ratings_result.get("source_status_counts", {}),
        "result_source_status_counts": results_result.get("source_status_counts", {}),
        "guardrails": {
            "current_ratings_used_as_historical": False,
            "current_statsbomb_live_data_used": False,
            "proxy_adjustments_enabled": False,
            "betting_recommendations": False,
        },
        "output_paths": {key: str(path) for key, path in paths.items()},
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    lines = [
        "# Historical International Calibration Seed",
        "",
        f"- Rating snapshot rows: `{manifest['historical_rating_snapshot_rows']}`",
        f"- Historical result rows: `{manifest['historical_results_rows']}`",
        f"- Matches with both ratings matched: `{manifest['historical_matches_with_ratings_rows']}`",
        f"- Rating source statuses: `{manifest['rating_source_status_counts']}`",
        f"- Result source statuses: `{manifest['result_source_status_counts']}`",
        "",
        "## Rating Match Status",
        "",
        _markdown_table(matched["rating_match_status"].value_counts().rename_axis("rating_match_status").reset_index(name="rows") if not matched.empty else pd.DataFrame()),
        "",
        "## Guardrails",
        "",
        "- Current ratings are not used as historical snapshots.",
        "- No current StatsBomb live data is used.",
        "- This seed creates calibration inputs only; it does not tune production defaults.",
    ]
    paths["summary"].write_text("\n".join(lines), encoding="utf-8")
    return {
        "snapshots": snapshots,
        "results": results,
        "matches_with_ratings": matched,
        "manifest": manifest,
        "paths": {key: str(path) for key, path in paths.items()},
        "run_dir": run_dir,
    }
