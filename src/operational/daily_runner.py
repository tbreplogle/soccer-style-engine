from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_ingestion.multi_league_football_data import download_football_data_leagues, normalize_multi_league_football_data
from src.models.leakage_audit import run_leakage_audit
from src.operational.defaults import OPERATIONAL_DEFAULTS, OperationalDefaults
from src.operational.run_manifest import build_run_manifest, write_run_manifest
from src.reports.projection_report import compare_club_projection_profiles
from src.reports.slate_report import build_club_slate_report, build_international_slate_report


def _split_csv(value: str | list[str] | tuple[str, ...] | None, default: tuple[str, ...]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _copy_if_exists(source: str | Path, target: Path) -> Path | None:
    src = Path(source)
    if not src.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, target)
    return target


def _row_counts(frame: pd.DataFrame) -> dict[str, Any]:
    counts: dict[str, Any] = {"total_rows": int(len(frame))}
    if {"league", "season"}.issubset(frame.columns):
        counts["by_league"] = {str(k): int(v) for k, v in frame.groupby("league").size().to_dict().items()}
    if "date" in frame and not frame.empty:
        counts["date_min"] = str(pd.to_datetime(frame["date"], errors="coerce").min().date())
        counts["date_max"] = str(pd.to_datetime(frame["date"], errors="coerce").max().date())
    return counts


def _first_matchup(results: pd.DataFrame) -> dict[str, Any] | None:
    if results.empty:
        return None
    general = results[results["projection_profile"].eq(OPERATIONAL_DEFAULTS.club.general_report_profile)]
    row = (general if not general.empty else results).iloc[0]
    return {"home": row["home_team"], "away": row["away_team"], "league": row.get("league"), "as_of_date": row.get("slate_date")}


def run_daily_pipeline(
    as_of_date: str,
    season_code: str | None = None,
    fallback_season_code: str | None = None,
    leagues: str | list[str] | None = None,
    output_root: str | Path = "outputs/runs",
    slate_type: str = "auto",
    max_matches: int | None = None,
    include_international: bool = False,
    international_input: str | Path | None = None,
    manual_club_matchups: str | Path | None = None,
    manual_international_matchups: str | Path | None = None,
    skip_download: bool = False,
    run_quick_audit: bool = False,
    raw_input_dir: str | Path = "data/raw/football-data",
    processed_output: str | Path = "data/processed/operational_current_match_results.csv",
    defaults: OperationalDefaults = OPERATIONAL_DEFAULTS,
) -> dict[str, Any]:
    club_defaults = defaults.club
    selected_season = season_code or club_defaults.default_current_season_code
    selected_fallback = fallback_season_code or club_defaults.fallback_season_code
    selected_leagues = _split_csv(leagues, club_defaults.default_leagues)
    selected_max = max_matches or club_defaults.max_default_matches
    run_id = as_of_date
    run_dir = Path(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    download_status: list[dict[str, Any]] = []
    raw_dir = Path(raw_input_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    if skip_download:
        warnings.append("Download skipped; using available local Football-Data CSVs.")
    else:
        download = download_football_data_leagues(
            season_code=selected_season,
            fallback_season_code=selected_fallback,
            leagues=selected_leagues,
            output_dir=raw_dir,
        )
        download_status = download.to_dict("records")
        failed = download[download["status"].ne("downloaded")] if not download.empty else download
        if not failed.empty:
            warnings.append("Some Football-Data downloads failed; continued with available local files.")
    normalized = normalize_multi_league_football_data(raw_dir, output_path=processed_output, season="")
    if normalized.empty:
        raise ValueError("No available Football-Data rows to normalize for the daily pipeline.")
    filtered = normalized[normalized["league"].isin(selected_leagues)].copy() if "league" in normalized else normalized.copy()
    if "data_source" in filtered.columns:
        season_mask = filtered["data_source"].astype(str).str.contains(f"_{selected_season}.csv", regex=False)
        if season_mask.any():
            filtered = filtered[season_mask].copy()
    if filtered.empty:
        raise ValueError("No normalized rows remained after applying requested leagues.")
    normalized_run_path = run_dir / "normalized_current_match_results.csv"
    filtered.to_csv(normalized_run_path, index=False)
    comparison_profiles = [
        club_defaults.general_report_profile,
        club_defaults.primary_wdl_profile,
        "total_goals",
        "market_anchored",
        "model_only",
    ]
    comparison_profiles = list(dict.fromkeys(comparison_profiles))
    slate_profiles = [club_defaults.general_report_profile]
    club = build_club_slate_report(
        normalized_run_path,
        as_of_date,
        projection_profiles=slate_profiles,
        output_dir=run_dir,
        projection_output_dir=run_dir,
        slate_type=slate_type,
        max_matches=selected_max,
        matchups_csv=manual_club_matchups,
    )
    generated = [str(club["markdown_path"]), str(club["csv_path"]), str(normalized_run_path)]
    comparison = None
    matchup = _first_matchup(club["results"])
    if matchup:
        comparison = compare_club_projection_profiles(
            normalized_run_path,
            matchup["home"],
            matchup["away"],
            matchup["as_of_date"] or as_of_date,
            profiles=comparison_profiles,
            output_dir=run_dir,
            projection_output_dir=run_dir,
            league=matchup.get("league"),
        )
        generated.extend([str(comparison["markdown_path"]), str(comparison["csv_path"])])
    audit = None
    if run_quick_audit:
        audit = run_leakage_audit(filtered, output_dir=run_dir)
        generated.append(str(audit["summary_path"]))
        if not audit["leakage_checks_passed"]:
            warnings.append("Quick leakage audit failed; inspect leakage_audit_summary.md.")
    international = None
    if include_international:
        if international_input and Path(international_input).exists():
            international = build_international_slate_report(
                international_input,
                as_of_date,
                matchups_csv=manual_international_matchups,
                output_dir=run_dir,
                projection_output_dir=run_dir,
                max_matches=selected_max,
            )
            generated.extend([str(international["markdown_path"]), str(international["csv_path"])])
        else:
            warnings.append("International requested but no processed international input exists; skipped international slate.")
    summary_path = write_run_summary(
        run_dir / "run_summary.md",
        run_date=as_of_date,
        data_sources=[str(raw_dir), str(normalized_run_path)],
        leagues=selected_leagues,
        row_counts=_row_counts(filtered),
        slate_type=str(club["slate_type"]),
        profiles=comparison_profiles,
        warnings=warnings,
        generated_files=generated,
        defaults=defaults,
    )
    generated.append(str(summary_path))
    manifest = build_run_manifest(
        run_id=run_id,
        run_date=as_of_date,
        input_files=[str(raw_dir), str(normalized_run_path)],
        leagues=selected_leagues,
        season_code=selected_season,
        downloaded_files_status=download_status,
        normalized_row_counts=_row_counts(filtered),
        slate_type=str(club["slate_type"]),
        profiles_run=comparison_profiles,
        defaults_used=defaults.to_dict(),
        guardrails_active=defaults.guardrails.__dict__,
        warnings=warnings,
        generated_output_paths=generated,
    )
    manifest_path = write_run_manifest(manifest, run_dir / "run_manifest.json")
    generated.append(str(manifest_path))
    return {
        "run_dir": run_dir,
        "manifest_path": manifest_path,
        "summary_path": summary_path,
        "manifest": manifest,
        "club": club,
        "comparison": comparison,
        "audit": audit,
        "international": international,
        "warnings": warnings,
        "generated_files": generated,
    }


def write_run_summary(
    path: str | Path,
    run_date: str,
    data_sources: list[str],
    leagues: list[str],
    row_counts: dict[str, Any],
    slate_type: str,
    profiles: list[str],
    warnings: list[str],
    generated_files: list[str],
    defaults: OperationalDefaults = OPERATIONAL_DEFAULTS,
) -> Path:
    lines = [
        "# Daily Pipeline Run Summary",
        "",
        f"Run date: {run_date}",
        f"Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Data Sources",
        "",
        *[f"- `{source}`" for source in data_sources],
        "",
        "## Scope",
        "",
        f"- Leagues included: {', '.join(leagues)}",
        f"- Row counts: `{row_counts}`",
        f"- Slate type: `{slate_type}`",
        "",
        "## Model Defaults",
        "",
        f"- General report view: `{defaults.club.general_report_profile}`",
        f"- Validated W/D/L context profile: `{defaults.club.primary_wdl_profile}`",
        f"- Baseline mode: `{defaults.club.default_baseline_mode}`",
        f"- Proxy adjustments enabled: `{defaults.club.proxy_adjustments_enabled}`",
        f"- Confidence language: `{defaults.club.confidence_language}`",
        f"- Profiles run: {', '.join(profiles)}",
        "",
        "## Guardrails",
        "",
        "- No betting recommendations or action language.",
        "- Confidence is Data Support / Risk Context, not certainty and not a betting signal.",
        "- Market gap is diagnostic context, not a betting recommendation.",
        "- Current free proxy style is not true tracking/event style.",
        "",
        "## Generated Files",
        "",
        *[f"- `{file}`" for file in generated_files],
        "",
        "## Warnings",
        "",
        *([f"- {warning}" for warning in warnings] if warnings else ["- None"]),
        "",
        "## Next Steps",
        "",
        "- Review slate context and risk flags before sharing.",
        "- Treat totals as less settled than W/D/L until more calibration work is done.",
        "- Keep UI and style visuals deferred until operational output is stable.",
        "",
    ]
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
