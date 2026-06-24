from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from time import perf_counter

import pandas as pd

from src.data_ingestion.multi_league_football_data import download_football_data_leagues, normalize_multi_league_football_data
from src.models.leakage_audit import run_leakage_audit
from src.operational.currentness import check_data_currentness
from src.operational.defaults import OPERATIONAL_DEFAULTS, OperationalDefaults
from src.operational.run_manifest import build_run_manifest, write_run_manifest
from src.operational.run_log import write_run_log
from src.operational.season_sanity import check_season_sanity
from src.reports.projection_report import compare_club_projection_profiles
from src.reports.slate_report import build_club_slate_report, build_international_slate_report


def _split_csv(value: str | list[str] | tuple[str, ...] | None, default: tuple[str, ...]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


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


def _policy_failure(status: str, policy: str) -> str | None:
    if policy == "fail-on-missing" and status == "missing":
        return "failed_missing_data"
    if policy == "fail-on-stale" and status in {"missing", "stale", "unsafe"}:
        return "failed_unsafe_data" if status == "unsafe" else "failed_missing_data" if status == "missing" else "failed_unsafe_data"
    if policy == "fail-on-unsafe" and status == "unsafe":
        return "failed_unsafe_data"
    return None


def _prepend_operational_header(path: str | Path, run_status: str, currentness: dict[str, Any], season: dict[str, Any], policy: str) -> None:
    target = Path(path)
    if not target.exists():
        return
    trust_warning = ""
    if currentness.get("currentness_status") in {"stale", "unsafe"} or run_status.startswith("failed"):
        trust_warning = "\n**Do not trust this slate until stale/unsafe data warnings are resolved or the run is explicitly historical.**\n"
    header = "\n".join([
        f"**Run status:** `{run_status}`",
        f"**Data currentness:** `{currentness.get('currentness_status', 'unknown')}`",
        f"**Season sanity:** `{season.get('season_sanity_status', 'unknown')}`",
        f"**Currentness policy:** `{policy}`",
        trust_warning,
        "",
    ])
    original = target.read_text(encoding="utf-8")
    target.write_text(original.replace("\n\n", "\n\n" + header, 1), encoding="utf-8")


def _log_row(
    run_id: str,
    run_date: str,
    status: str,
    currentness_status: str,
    season_status: str,
    leagues: list[str],
    row_count: int,
    slate_type: str,
    outputs_written: int,
    warnings_count: int,
    error_message: str,
    duration_seconds: float,
    timing: dict[str, float],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "run_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "currentness_status": currentness_status,
        "season_sanity_status": season_status,
        "leagues": ",".join(leagues),
        "row_count": row_count,
        "slate_type": slate_type,
        "outputs_written": outputs_written,
        "warnings_count": warnings_count,
        "error_message": error_message,
        "duration_seconds": round(duration_seconds, 3),
        "download_seconds": round(timing.get("download_seconds", 0.0), 3),
        "normalization_seconds": round(timing.get("normalization_seconds", 0.0), 3),
        "slate_seconds": round(timing.get("slate_seconds", 0.0), 3),
        "audit_seconds": round(timing.get("audit_seconds", 0.0), 3),
        "total_duration_seconds": round(timing.get("total_duration_seconds", duration_seconds), 3),
    }


def _warning_groups(warnings: list[str], currentness: dict[str, Any], international_requested: bool = False) -> dict[str, list[str]]:
    groups = {
        "blocking_problems": [],
        "data_currentness_notes": [],
        "league_completion_notes": [],
        "processed_raw_freshness_notes": [],
        "international_notes": [],
        "performance_notes": [],
        "guardrail_notes": [
            "No betting recommendations or action language.",
            "Proxy score adjustments remain disabled by default.",
        ],
    }
    for warning in warnings:
        text = warning.lower()
        if "blocked" in text or "unsafe" in text or "failed" in text:
            groups["blocking_problems"].append(warning)
        elif "appears season-complete" in text or "completed" in text:
            groups["league_completion_notes"].append(warning)
        elif "processed" in text or "raw" in text or "normaliz" in text:
            groups["processed_raw_freshness_notes"].append(warning)
        elif "international" in text:
            groups["international_notes"].append(warning)
        else:
            groups["data_currentness_notes"].append(warning)
    for league in currentness.get("leagues_completed", []):
        note = f"{league} appears season-complete, not stale."
        if note not in groups["league_completion_notes"]:
            groups["league_completion_notes"].append(note)
    if international_requested and not groups["international_notes"]:
        groups["international_notes"].append("International requested and handled according to available local data.")
    return groups


def _drop_obsolete_processed_warnings(warnings: list[str], currentness: dict[str, Any]) -> list[str]:
    if currentness.get("processed_freshness_status") != "fresh":
        return warnings
    return [
        warning
        for warning in warnings
        if "Processed data is older than relevant raw data" not in warning
        and "Processed data is missing but raw data exists" not in warning
    ]


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
    currentness_policy: str = "warn",
    historical_mode: bool = False,
    run_log_dir: str | Path = "outputs/run_logs",
    skip_profile_comparison: bool = False,
    profiles: str | list[str] | None = None,
    reuse_processed_if_fresh: bool = False,
    build_viewer: bool = False,
    viewer_output_dir: str | Path = "outputs/viewer",
    defaults: OperationalDefaults = OPERATIONAL_DEFAULTS,
) -> dict[str, Any]:
    started = perf_counter()
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
    timing: dict[str, float] = {
        "download_seconds": 0.0,
        "normalization_seconds": 0.0,
        "slate_seconds": 0.0,
        "audit_seconds": 0.0,
        "total_duration_seconds": 0.0,
    }
    generated: list[str] = []
    viewer_result: dict[str, Any] | None = None
    row_count = 0
    resolved_slate_type = slate_type
    status = "success"
    error_message = ""
    raw_dir = Path(raw_input_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    comparison_profiles = list(dict.fromkeys(_split_csv(profiles, (
        club_defaults.general_report_profile,
        club_defaults.primary_wdl_profile,
        "total_goals",
        "market_anchored",
        "model_only",
    ))))
    currentness = check_data_currentness(raw_dir, processed_output, as_of_date, selected_season, selected_leagues, historical_mode=historical_mode or slate_type == "historical", slate_type=slate_type)
    season = check_season_sanity(selected_season, as_of_date, historical_mode=historical_mode or slate_type == "historical")
    warnings.extend(currentness["warnings"])
    if skip_download:
        warnings.append("Download skipped; using available local Football-Data CSVs.")
    else:
        try:
            t0 = perf_counter()
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
        except Exception as exc:
            warnings.append(f"Football-Data download failed; continued with local files if usable: {exc}")
        finally:
            timing["download_seconds"] = perf_counter() - t0
        currentness = check_data_currentness(raw_dir, processed_output, as_of_date, selected_season, selected_leagues, historical_mode=historical_mode or slate_type == "historical", slate_type=slate_type)
        warnings.extend([w for w in currentness["warnings"] if w not in warnings])
    failure = _policy_failure(currentness["currentness_status"], currentness_policy)
    club = comparison = audit = international = None
    normalized_run_path = run_dir / "normalized_current_match_results.csv"
    try:
        if failure:
            status = failure
            error_message = f"Currentness policy {currentness_policy} blocked run with status {currentness['currentness_status']}."
        else:
            t0 = perf_counter()
            if reuse_processed_if_fresh and skip_download and currentness.get("processed_freshness_status") == "fresh" and Path(processed_output).exists():
                normalized = pd.read_csv(processed_output)
                warnings.append("Reused fresh processed data; skipped normalization.")
            else:
                normalized = normalize_multi_league_football_data(raw_dir, output_path=processed_output, season="")
                currentness = check_data_currentness(raw_dir, processed_output, as_of_date, selected_season, selected_leagues, historical_mode=historical_mode or slate_type == "historical", slate_type=slate_type)
                warnings = _drop_obsolete_processed_warnings(warnings, currentness)
                warnings.extend([w for w in currentness["warnings"] if w not in warnings])
            timing["normalization_seconds"] = perf_counter() - t0
            if normalized.empty:
                status = "failed_missing_data"
                error_message = "No available Football-Data rows to normalize for the daily pipeline."
            else:
                filtered = normalized[normalized["league"].isin(selected_leagues)].copy() if "league" in normalized else normalized.copy()
                if "data_source" in filtered.columns:
                    season_mask = filtered["data_source"].astype(str).str.contains(f"_{selected_season}.csv", regex=False)
                    if season_mask.any():
                        filtered = filtered[season_mask].copy()
                if filtered.empty:
                    status = "failed_missing_data"
                    error_message = "No normalized rows remained after applying requested leagues."
                else:
                    row_count = len(filtered)
                    filtered.to_csv(normalized_run_path, index=False)
                    generated.append(str(normalized_run_path))
                    slate_profiles = [club_defaults.general_report_profile]
                    t0 = perf_counter()
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
                    timing["slate_seconds"] += perf_counter() - t0
                    resolved_slate_type = str(club["slate_type"])
                    generated.extend([str(club["markdown_path"]), str(club["csv_path"])])
                    matchup = _first_matchup(club["results"])
                    if matchup and not skip_profile_comparison:
                        t0 = perf_counter()
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
                        timing["slate_seconds"] += perf_counter() - t0
                        generated.extend([str(comparison["markdown_path"]), str(comparison["csv_path"])])
                    if run_quick_audit:
                        t0 = perf_counter()
                        audit = run_leakage_audit(filtered, output_dir=run_dir)
                        timing["audit_seconds"] = perf_counter() - t0
                        generated.append(str(audit["summary_path"]))
                        if not audit["leakage_checks_passed"]:
                            warnings.append("Quick leakage audit failed; inspect leakage_audit_summary.md.")
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
                    if currentness["currentness_status"] in {"stale", "probably_current"} or warnings:
                        status = "success_with_warnings"
    except Exception as exc:  # defensive recovery: write manifest/log even on runtime failure
        status = "failed_runtime_error"
        error_message = str(exc)
        warnings.append(f"Runtime error: {exc}")
    row_counts = {"total_rows": row_count}
    if normalized_run_path.exists():
        try:
            row_counts = _row_counts(pd.read_csv(normalized_run_path))
        except Exception:
            pass
    timing["total_duration_seconds"] = perf_counter() - started
    warning_groups = _warning_groups(warnings + ([error_message] if error_message else []), currentness, include_international)
    viewer_output_path = str(Path(viewer_output_dir) / "index.html") if build_viewer else ""
    if viewer_output_path:
        generated.append(viewer_output_path)
    summary_path = write_run_summary(
        run_dir / "run_summary.md",
        run_date=as_of_date,
        data_sources=[str(raw_dir), str(normalized_run_path)],
        leagues=selected_leagues,
        row_counts=row_counts,
        slate_type=resolved_slate_type,
        profiles=comparison_profiles,
        warnings=warnings + ([error_message] if error_message else []),
        warning_groups=warning_groups,
        generated_files=generated,
        defaults=defaults,
        run_status=status,
        currentness=currentness,
        season_sanity=season,
        currentness_policy=currentness_policy,
        timing=timing,
        viewer_output_path=viewer_output_path,
    )
    generated.append(str(summary_path))
    manifest = build_run_manifest(
        run_id=run_id,
        run_date=as_of_date,
        input_files=[str(raw_dir), str(normalized_run_path)],
        leagues=selected_leagues,
        season_code=selected_season,
        downloaded_files_status=download_status,
        normalized_row_counts=row_counts,
        slate_type=resolved_slate_type,
        profiles_run=comparison_profiles,
        defaults_used=defaults.to_dict(),
        guardrails_active=defaults.guardrails.__dict__,
        warnings=warnings,
        generated_output_paths=generated,
        status=status,
        currentness_status=currentness["currentness_status"],
        season_sanity_status=season["season_sanity_status"],
        error_message=error_message,
        timing=timing,
        processed_freshness={
            "processed_freshness_status": currentness.get("processed_freshness_status"),
            "raw_latest_modified_at": currentness.get("raw_latest_modified_at"),
            "processed_modified_at": currentness.get("processed_modified_at"),
            "files_compared": currentness.get("files_compared"),
        },
        viewer_output_path=viewer_output_path,
    )
    manifest_path = write_run_manifest(manifest, run_dir / "run_manifest.json")
    generated.append(str(manifest_path))
    if build_viewer:
        try:
            from src.viewer.static_viewer import build_static_viewer

            viewer_result = build_static_viewer(output_root, viewer_output_dir)
            if viewer_result.get("safety_scan_status") == "warning":
                warnings.append("Viewer safety scan found action-language warnings; inspect viewer output.")
        except Exception as exc:
            warnings.append(f"Viewer generation failed: {exc}")
        if warnings and status == "success":
            status = "success_with_warnings"
        warning_groups = _warning_groups(warnings + ([error_message] if error_message else []), currentness, include_international)
        summary_path = write_run_summary(
            run_dir / "run_summary.md",
            run_date=as_of_date,
            data_sources=[str(raw_dir), str(normalized_run_path)],
            leagues=selected_leagues,
            row_counts=row_counts,
            slate_type=resolved_slate_type,
            profiles=comparison_profiles,
            warnings=warnings + ([error_message] if error_message else []),
            warning_groups=warning_groups,
            generated_files=generated,
            defaults=defaults,
            run_status=status,
            currentness=currentness,
            season_sanity=season,
            currentness_policy=currentness_policy,
            timing=timing,
            viewer_output_path=viewer_output_path,
        )
        manifest["status"] = status
        manifest["warnings"] = warnings
        manifest["generated_output_paths"] = generated
        manifest["viewer_output_path"] = viewer_output_path
        manifest_path = write_run_manifest(manifest, run_dir / "run_manifest.json")
    for path in generated:
        if Path(path).name.endswith(".md") and Path(path).name != "run_summary.md":
            _prepend_operational_header(path, status, currentness, season, currentness_policy)
    log_paths = write_run_log(
        _log_row(
            run_id,
            as_of_date,
            status,
            currentness["currentness_status"],
            season["season_sanity_status"],
            selected_leagues,
            row_count,
            resolved_slate_type,
            len(generated),
            len(warnings),
            error_message,
            perf_counter() - started,
            timing,
        ),
        output_dir=run_log_dir,
    )
    return {
        "status": status,
        "run_dir": run_dir,
        "manifest_path": manifest_path,
        "summary_path": summary_path,
        "manifest": manifest,
        "club": club,
        "comparison": comparison,
        "audit": audit,
        "international": international,
        "currentness": currentness,
        "season_sanity": season,
        "warnings": warnings,
        "generated_files": generated,
        "run_log_paths": log_paths,
        "timing": timing,
        "warning_groups": warning_groups,
        "viewer": viewer_result,
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
    warning_groups: dict[str, list[str]] | None,
    generated_files: list[str],
    defaults: OperationalDefaults = OPERATIONAL_DEFAULTS,
    run_status: str = "success",
    currentness: dict[str, Any] | None = None,
    season_sanity: dict[str, Any] | None = None,
    currentness_policy: str = "warn",
    timing: dict[str, float] | None = None,
    viewer_output_path: str = "",
) -> Path:
    currentness = currentness or {"currentness_status": "unknown"}
    season_sanity = season_sanity or {"season_sanity_status": "unknown"}
    trust_warning = currentness.get("currentness_status") in {"stale", "unsafe"} or run_status.startswith("failed")
    warning_groups = warning_groups or {}
    timing = timing or {}
    lines = [
        "# Daily Pipeline Run Summary",
        "",
        f"Run status: `{run_status}`",
        f"Data currentness status: `{currentness.get('currentness_status', 'unknown')}`",
        f"Season sanity status: `{season_sanity.get('season_sanity_status', 'unknown')}`",
        f"Currentness policy: `{currentness_policy}`",
        "**Do not trust this slate until stale/unsafe data warnings are resolved.**" if trust_warning else "Slate trust note: data checks did not block this run.",
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
        f"- Timing seconds: `{timing}`",
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
        "## Viewer",
        "",
        f"- Static viewer: `{viewer_output_path}`" if viewer_output_path else "- Static viewer: not requested for this run.",
        "",
        "## Warning Groups",
        "",
    ]
    for title, values in [
        ("Blocking Problems", warning_groups.get("blocking_problems", [])),
        ("Data Currentness Notes", warning_groups.get("data_currentness_notes", [])),
        ("League Completion Notes", warning_groups.get("league_completion_notes", [])),
        ("Processed/Raw Freshness Notes", warning_groups.get("processed_raw_freshness_notes", [])),
        ("International Notes", warning_groups.get("international_notes", [])),
        ("Performance Notes", warning_groups.get("performance_notes", [])),
        ("Guardrail Notes", warning_groups.get("guardrail_notes", [])),
    ]:
        lines.extend([f"### {title}", ""])
        lines.extend([f"- {value}" for value in values] if values else ["- None"])
        lines.append("")
    lines.extend([
        "",
        "## Next Steps",
        "",
        "- Review slate context and risk flags before sharing.",
        "- Treat totals as less settled than W/D/L until more calibration work is done.",
        "- Keep UI and style visuals deferred until operational output is stable.",
        "",
    ])
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
