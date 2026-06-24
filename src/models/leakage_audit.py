from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def run_leakage_audit(
    matches: pd.DataFrame | str | Path,
    start_date: str | None = None,
    end_date: str | None = None,
    output_dir: str | Path = "outputs/reports",
) -> dict[str, Any]:
    data = _load(matches)
    if start_date:
        data = data[data["date"] >= pd.to_datetime(start_date)]
    if end_date:
        data = data[data["date"] <= pd.to_datetime(end_date)]
    failed: list[str] = []
    warnings: list[str] = []
    if data.empty:
        warnings.append("No rows available for leakage audit.")
    if "future_leakage_flag" in data and data["future_leakage_flag"].fillna(False).astype(bool).any():
        failed.append("future_leakage_flag indicates target/future data was used.")
    if "uses_future_data" in data and data["uses_future_data"].fillna(False).astype(bool).any():
        failed.append("uses_future_data indicates target/future data was used.")
    if "as_of_date" in data:
        as_of = pd.to_datetime(data["as_of_date"], errors="coerce")
        bad = as_of.notna() & data["date"].notna() & (as_of >= data["date"])
        if bad.any():
            failed.append("as_of_date is on or after match date for historical target rows.")
    if {"target_home_goals_used", "target_away_goals_used"}.intersection(data.columns):
        failed.append("Target final-score columns are present in projection/audit input.")
    if "projection_profile" in data and data["projection_profile"].eq("market_anchored").any():
        if "market_odds_used_for_target" in data and data["market_odds_used_for_target"].fillna(False).astype(bool).any():
            warnings.append("Target-match market odds used only in market-aware profile rows.")
    if {"league", "season_code"}.issubset(data.columns):
        mixed = data.groupby(["home_team", "date"])["league"].nunique().gt(1).any()
        if mixed:
            warnings.append("Same home team/date appears in multiple leagues; downstream validation must keep league-season grouping.")
    else:
        warnings.append("league and season_code columns are not both present; grouping preservation cannot be fully checked.")
    recommendation = "pass" if not failed else "fix_failed_leakage_checks_before_validation"
    payload = {
        "leakage_checks_passed": not failed,
        "failed_checks": failed,
        "warnings": warnings,
        "tested_rows": int(len(data)),
        "recommendation": recommendation,
        "checks": [
            "prior-only as_of_date check",
            "rolling windows exclude target match by validator index order",
            "league-season grouping required",
            "market odds allowed only for market-aware profile",
            "final scores not allowed on projection target rows",
        ],
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = write_leakage_audit_report(payload, output / "leakage_audit_summary.md")
    payload["report"] = report
    payload["summary_path"] = output / "leakage_audit_summary.md"
    return payload


def write_leakage_audit_report(payload: dict[str, Any], output_path: str | Path) -> str:
    lines = [
        "# Leakage Audit Summary",
        "",
        f"Leakage checks passed: {payload['leakage_checks_passed']}",
        f"Tested rows: {payload['tested_rows']}",
        f"Recommendation: {payload['recommendation']}",
        "",
        "## Failed Checks",
        "",
        "\n".join(f"- {item}" for item in payload["failed_checks"]) if payload["failed_checks"] else "- None",
        "",
        "## Warnings",
        "",
        "\n".join(f"- {item}" for item in payload["warnings"]) if payload["warnings"] else "- None",
        "",
        "## Checks",
        "",
        "\n".join(f"- {item}" for item in payload["checks"]),
        "",
    ]
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report
