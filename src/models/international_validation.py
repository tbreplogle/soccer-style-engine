from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.data_ingestion.international_data import build_international_match_dataset
from src.models.international_backtest import run_international_backtest


def run_international_validation(
    statsbomb_root: str | Path = "data/raw/statsbomb-open-data/data",
    competition_name: str | None = None,
    season_id: str | int | None = None,
    max_matches: int = 64,
    output_dir: str | Path = "outputs/reports",
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    root = Path(statsbomb_root)
    if not root.exists():
        payload = {
            "status": "local_data_missing",
            "matches": 0,
            "sparse_warning_rate": None,
            "confidence_bucket_performance": "not evaluated",
            "club_international_separation": True,
            "neutral_site_handling": "not evaluated",
            "historical_event_labeling": "not evaluated",
            "current_readiness_claim": "not claimed",
        }
        report = write_international_validation_report(payload, output / "international_validation_summary.md")
        payload["report"] = report
        payload["summary_path"] = output / "international_validation_summary.md"
        return payload
    data = build_international_match_dataset(
        statsbomb_root=root,
        competition_name=competition_name,
        season_id=season_id,
        max_matches=max_matches,
        output_path=None,
        include_football_data_folder=None,
    )
    if data.empty:
        payload = {
            "status": "no_eligible_matches",
            "matches": 0,
            "sparse_warning_rate": None,
            "confidence_bucket_performance": "not evaluated",
            "club_international_separation": True,
            "neutral_site_handling": "not evaluated",
            "historical_event_labeling": "not evaluated",
            "current_readiness_claim": "not claimed",
        }
        report = write_international_validation_report(payload, output / "international_validation_summary.md")
        payload["report"] = report
        payload["summary_path"] = output / "international_validation_summary.md"
        return payload
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    valid = data.dropna(subset=["date"]).sort_values("date")
    backtest = run_international_backtest(
        valid,
        start_date=str(valid["date"].min().date()),
        end_date=str(valid["date"].max().date()),
        competition_name=competition_name,
        season_id=season_id,
        output_dir=output,
        min_prior_matches=1,
    )
    results = backtest["results"]
    sparse_rate = float(results["sparse_sample_warning"].mean()) if not results.empty and "sparse_sample_warning" in results else None
    buckets = results.groupby("confidence_label").size().to_dict() if not results.empty and "confidence_label" in results else {}
    historical_event_labeling = "ok" if data["data_mode"].astype(str).str.contains("historical|true_event_style_historical").all() else "review"
    neutral_site_handling = "present" if "neutral_site" in data and data["neutral_site"].notna().any() else "missing"
    payload = {
        "status": "evaluated",
        "matches": int(len(valid)),
        "sparse_warning_rate": sparse_rate,
        "confidence_bucket_performance": buckets,
        "club_international_separation": bool(data["country_or_team_type"].eq("national_team").all()),
        "neutral_site_handling": neutral_site_handling,
        "historical_event_labeling": historical_event_labeling,
        "current_readiness_claim": "not claimed",
    }
    report = write_international_validation_report(payload, output / "international_validation_summary.md")
    payload["report"] = report
    payload["summary_path"] = output / "international_validation_summary.md"
    return payload


def write_international_validation_report(payload: dict[str, Any], output_path: str | Path) -> str:
    lines = [
        "# International Validation Summary",
        "",
        f"Status: {payload['status']}",
        f"Matches evaluated: {payload['matches']}",
        f"Sparse warning rate: {payload['sparse_warning_rate']}",
        f"Confidence buckets: {payload['confidence_bucket_performance']}",
        f"Club/international separation: {payload['club_international_separation']}",
        f"Neutral-site handling: {payload['neutral_site_handling']}",
        f"Historical event labeling: {payload['historical_event_labeling']}",
        f"Current international readiness claim: {payload['current_readiness_claim']}",
        "",
        "This report is a sanity check for historical international data only; it does not mix club ratings or claim current international readiness.",
        "",
    ]
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report
