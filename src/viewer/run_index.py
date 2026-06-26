from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RUN_OUTPUT_NAMES = (
    "run_manifest.json",
    "run_summary.md",
    "club_slate_projections.csv",
    "international_slate_projections.csv",
    "projection_profile_comparison.csv",
    "club_slate_report.md",
    "international_slate_report.md",
    "projection_profile_comparison.md",
    "leakage_audit_summary.md",
)

CHECKPOINT_OUTPUT_NAMES = (
    "projection_checkpoint_manifest.json",
    "projection_checkpoint_summary.md",
    "projection_checkpoint_rows.csv",
    "projection_checkpoint_flags.csv",
    "poisson/poisson_summary.md",
    "poisson/poisson_1x2.csv",
    "poisson/poisson_totals.csv",
    "poisson/poisson_btts.csv",
    "poisson/poisson_clean_sheets.csv",
    "poisson/poisson_match_summary.csv",
    "poisson/poisson_correct_score_matrix.csv",
)

CURRENT_INTERNATIONAL_OUTPUT_NAMES = (
    "current_international_manifest.json",
    "current_international_source_summary.md",
    "current_international_slate.csv",
    "current_international_projections.csv",
    "current_international_projection_report.md",
    "source_audit/source_audit.csv",
    "source_audit/fixture_coverage.csv",
    "source_audit/rating_coverage.csv",
    "source_audit/stat_coverage.csv",
    "source_audit/match_data_coverage.csv",
    "source_audit/source_audit_summary.md",
    "fixture_readiness/fixture_readiness_summary.md",
    "fixture_readiness/resolved_fixtures.csv",
    "fixture_readiness/unresolved_fixtures.csv",
    "fixture_readiness/projection_eligible_fixtures.csv",
    "fixture_readiness/projection_skipped_fixtures.csv",
    "slate_selection/slate_selection_summary.md",
    "slate_selection/selected_fixtures.csv",
    "slate_selection/skipped_by_date_fixtures.csv",
    "slate_selection/skipped_unresolved_fixtures.csv",
    "slate_selection/all_resolved_fixtures.csv",
    "fixture_deduplication/fixture_deduplication_summary.md",
    "fixture_deduplication/deduplicated_fixtures.csv",
    "fixture_deduplication/duplicate_fixtures.csv",
    "fixture_deduplication/possible_duplicate_review.csv",
    "fixture_deduplication/source_priority_summary.csv",
    "fixture_deduplication/dedupe_consistency_check.csv",
    "fixture_deduplication/projection_checkpoint_consistency.md",
    "cache_seed/cache_seed_summary.md",
    "cache_seed/fixture_seed_results.csv",
    "cache_seed/rating_seed_results.csv",
    "cache_seed/stat_seed_results.csv",
    "cache_seed/source_fetch_results.csv",
    "cache_seed/rating_parse_diagnostics.csv",
    "cache_seed/parsed_fixture_rows.csv",
    "cache_seed/parsed_rating_rows.csv",
    "cache_seed/parsed_stat_rows.csv",
    "candidate_preview/candidate_projection_comparison.csv",
    "candidate_preview/candidate_projection_comparison_summary.md",
    "scoreline_candidate_preview/candidate_projection_comparison.csv",
    "scoreline_candidate_preview/candidate_projection_comparison_summary.md",
)

CALIBRATION_OUTPUT_NAMES = (
    "calibration_manifest.json",
    "baseline_calibration_summary.md",
    "wdl_calibration.csv",
    "totals_calibration.csv",
    "probability_buckets.csv",
    "scoreline_calibration.csv",
    "baseline_tuning/baseline_tuning_summary.md",
    "baseline_tuning/baseline_tuning_grid.csv",
    "baseline_tuning/baseline_tuning_best_candidates.csv",
    "baseline_tuning/baseline_tuning_manifest.json",
    "baseline_tuning/candidate_model_config.json",
    "baseline_tuning/train_metrics.csv",
    "baseline_tuning/holdout_metrics.csv",
    "baseline_tuning/tuning_holdout_summary.md",
)

SCORELINE_DIAGNOSTIC_OUTPUT_NAMES = (
    "scoreline_diagnostics_summary.md",
    "scoreline_metrics.csv",
    "scoreline_topk_metrics.csv",
    "team_goal_band_calibration.csv",
    "total_goal_band_calibration.csv",
    "actual_score_rankings.csv",
    "scoreline_diagnostics_manifest.json",
)

GRADING_OUTPUT_NAMES = (
    "current_projection_grading_summary.md",
    "graded_matches.csv",
    "scoreline_miss_types.csv",
    "result_grading_manifest.json",
)

HISTORICAL_SEED_OUTPUT_NAMES = (
    "historical_seed_summary.md",
    "historical_rating_snapshots.csv",
    "historical_results.csv",
    "historical_matches_with_ratings.csv",
    "historical_seed_manifest.json",
)

CLUB_READINESS_OUTPUT_NAMES = (
    "league_readiness_summary.md",
    "league_readiness_by_league.csv",
    "club_data_inventory.csv",
    "club_projection_readiness.csv",
    "club_calibration_readiness.csv",
    "league_readiness_manifest.json",
    "club_slate_projections.csv",
    "club_slate_report.md",
)


def _empty_entry(run_dir: Path, error: str = "") -> dict[str, Any]:
    present = sorted(path.name for path in run_dir.iterdir()) if run_dir.exists() and run_dir.is_dir() else []
    return {
        "entry_type": "daily_run",
        "run_date": run_dir.name,
        "run_id": run_dir.name,
        "generated_at": "",
        "status": "missing_manifest" if error != "empty_run_folder" else "empty_run_folder",
        "currentness_status": "unknown",
        "season_sanity_status": "unknown",
        "leagues": [],
        "row_count": 0,
        "slate_type": "unknown",
        "warnings_count": 0,
        "warnings": [],
        "output_files_present": present,
        "manifest_path": "",
        "summary_path": str(run_dir / "run_summary.md") if (run_dir / "run_summary.md").exists() else "",
        "run_dir": str(run_dir),
        "error": error,
    }


def _manifest_entry(run_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry = _empty_entry(run_dir, "malformed_manifest")
        entry["status"] = "malformed_manifest"
        entry["manifest_path"] = str(manifest_path)
        entry["error"] = str(exc)
        return entry

    row_counts = manifest.get("normalized_row_counts") or {}
    warnings = manifest.get("warnings") or []
    summary_path = run_dir / "run_summary.md"
    present = [name for name in RUN_OUTPUT_NAMES if (run_dir / name).exists()]
    return {
        "entry_type": "daily_run",
        "run_date": str(manifest.get("run_date") or run_dir.name),
        "run_id": str(manifest.get("run_id") or run_dir.name),
        "generated_at": str(manifest.get("generated_at") or ""),
        "status": str(manifest.get("status") or "unknown"),
        "currentness_status": str(manifest.get("currentness_status") or "unknown"),
        "season_sanity_status": str(manifest.get("season_sanity_status") or "unknown"),
        "leagues": list(manifest.get("leagues") or []),
        "row_count": int(row_counts.get("total_rows") or 0),
        "slate_type": str(manifest.get("slate_type") or "unknown"),
        "warnings_count": len(warnings),
        "warnings": warnings,
        "output_files_present": present,
        "manifest_path": str(manifest_path),
        "summary_path": str(summary_path) if summary_path.exists() else "",
        "run_dir": str(run_dir),
        "error": str(manifest.get("error_message") or ""),
    }


def _checkpoint_entry(checkpoint_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry = _empty_entry(checkpoint_dir, "malformed_checkpoint_manifest")
        entry["entry_type"] = "projection_checkpoint"
        entry["status"] = "malformed_checkpoint_manifest"
        entry["manifest_path"] = str(manifest_path)
        entry["error"] = str(exc)
        return entry

    present = [name for name in CHECKPOINT_OUTPUT_NAMES if (checkpoint_dir / name).exists()]
    warnings_count = int(manifest.get("warning_count") or 0)
    slate_selection = manifest.get("current_projection_slate_selection") or {}
    current_paths = manifest.get("current_projection_output_paths") or {}
    dedupe = manifest.get("current_projection_deduplication") or {}
    return {
        "entry_type": "projection_checkpoint",
        "run_date": str(manifest.get("run_date") or checkpoint_dir.name),
        "run_id": str(manifest.get("run_id") or f"projection_checkpoint_{checkpoint_dir.name}"),
        "generated_at": str(manifest.get("generated_at") or ""),
        "status": str(manifest.get("status") or "unknown"),
        "currentness_status": "projection_checkpoint",
        "season_sanity_status": "not_applicable",
        "leagues": [],
        "row_count": int(manifest.get("rows_reviewed") or 0),
        "real_rows_reviewed": int(manifest.get("real_rows_reviewed") or 0),
        "manual_rows_reviewed": int(manifest.get("manual_rows_reviewed") or 0),
        "sample_rows_reviewed": int(manifest.get("sample_rows_reviewed") or 0),
        "poisson_match_count": int(_poisson_match_count(checkpoint_dir)),
        "slate_type": "projection_checkpoint",
        "slate_window": str(manifest.get("slate_window") or slate_selection.get("effective_slate_window") or ""),
        "selected_date_range": str(slate_selection.get("selected_date_range") or ""),
        "selected_fixture_count": int(slate_selection.get("selected_fixtures") or 0),
        "skipped_by_date_fixtures": int(slate_selection.get("skipped_by_date_fixtures") or 0),
        "skipped_past_fixtures": int(slate_selection.get("skipped_past_fixtures") or 0),
        "skipped_future_outside_window_fixtures": int(slate_selection.get("skipped_future_outside_window_fixtures") or 0),
        "skipped_unresolved_fixtures": int(slate_selection.get("skipped_unresolved_fixtures") or 0),
        "default_used_next_upcoming": bool(slate_selection.get("default_used_next_upcoming")),
        "fixture_rows_before_dedupe": int(dedupe.get("fixture_rows_before_dedupe") or 0),
        "fixture_rows_after_dedupe": int(dedupe.get("fixture_rows_after_dedupe") or 0),
        "duplicate_rows_skipped": int(dedupe.get("duplicate_rows_skipped") or 0),
        "possible_duplicate_review_rows": int(dedupe.get("possible_duplicate_review_rows") or 0),
        "warnings_count": warnings_count,
        "warnings": [f"{warnings_count} projection checkpoint warning flags"] if warnings_count else [],
        "output_files_present": present,
        "manifest_path": str(manifest_path),
        "summary_path": str(checkpoint_dir / "projection_checkpoint_summary.md") if (checkpoint_dir / "projection_checkpoint_summary.md").exists() else "",
        "run_dir": str(checkpoint_dir),
        "error": "",
        "source_projection_file": str(manifest.get("source_projection_file") or ""),
        "current_projection_output_paths": current_paths,
    }


def _poisson_match_count(checkpoint_dir: Path) -> int:
    path = checkpoint_dir / "poisson" / "poisson_match_summary.csv"
    if not path.exists():
        return 0
    try:
        return max(0, sum(1 for _ in path.open("r", encoding="utf-8-sig")) - 1)
    except OSError:
        return 0


def _current_international_entry(run_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry = _empty_entry(run_dir, "malformed_current_international_manifest")
        entry["entry_type"] = "current_international_run"
        entry["status"] = "malformed_current_international_manifest"
        entry["manifest_path"] = str(manifest_path)
        entry["error"] = str(exc)
        return entry

    present = [name for name in CURRENT_INTERNATIONAL_OUTPUT_NAMES if (run_dir / name).exists()]
    return {
        "entry_type": "current_international_run",
        "run_date": str(manifest.get("as_of_date") or run_dir.name),
        "run_id": str(manifest.get("run_id") or f"current_international_{run_dir.name}"),
        "generated_at": str(manifest.get("generated_at") or ""),
        "status": str(manifest.get("strict_real_data_status") or manifest.get("world_cup_readiness_status") or "unknown"),
        "currentness_status": str(manifest.get("world_cup_readiness_status") or "current_international"),
        "season_sanity_status": "not_applicable",
        "leagues": [],
        "row_count": int(manifest.get("projection_rows") or manifest.get("slate_rows") or manifest.get("fixture_count") or 0),
        "real_rows_reviewed": int(manifest.get("real_fixture_count") or 0),
        "manual_rows_reviewed": int(manifest.get("manual_fixture_count") or 0),
        "sample_rows_reviewed": int(manifest.get("sample_fixture_count") or 0),
        "resolved_rows": int(manifest.get("resolved_rows") or manifest.get("resolved_fixtures") or 0),
        "unresolved_rows": int(manifest.get("unresolved_rows") or manifest.get("unresolved_placeholders") or 0),
        "projected_rows": int(manifest.get("projected_rows") or manifest.get("projection_rows") or 0),
        "skipped_placeholder_rows": int(manifest.get("skipped_placeholder_rows") or 0),
        "poisson_match_count": int(_poisson_match_count(run_dir)),
        "slate_type": "current_international_run",
        "slate_window": str(manifest.get("effective_slate_window") or manifest.get("slate_window") or ""),
        "selected_date_range": str(manifest.get("selected_date_range") or ""),
        "selected_fixture_count": int(manifest.get("selected_fixture_count") or 0),
        "skipped_by_date_fixtures": int(manifest.get("skipped_by_date_fixtures") or 0),
        "skipped_past_fixtures": int(manifest.get("skipped_past_fixtures") or 0),
        "skipped_future_outside_window_fixtures": int(manifest.get("skipped_future_outside_window_fixtures") or 0),
        "skipped_unresolved_fixtures": int(manifest.get("skipped_unresolved_fixtures") or 0),
        "default_used_next_upcoming": bool((manifest.get("slate_selection") or {}).get("default_used_next_upcoming")),
        "fixture_rows_before_dedupe": int(manifest.get("fixture_rows_before_dedupe") or 0),
        "fixture_rows_after_dedupe": int(manifest.get("fixture_rows_after_dedupe") or 0),
        "duplicate_rows_skipped": int(manifest.get("duplicate_rows_skipped") or 0),
        "possible_duplicate_review_rows": int(manifest.get("possible_duplicate_review_rows") or 0),
        "warnings_count": len(manifest.get("warnings") or []) + len(manifest.get("strict_real_data_warnings") or []),
        "warnings": list(manifest.get("warnings") or []) + list(manifest.get("strict_real_data_warnings") or []),
        "output_files_present": present,
        "manifest_path": str(manifest_path),
        "summary_path": str(run_dir / "source_audit" / "source_audit_summary.md") if (run_dir / "source_audit" / "source_audit_summary.md").exists() else "",
        "run_dir": str(run_dir),
        "error": "",
    }


def _calibration_entry(run_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry = _empty_entry(run_dir, "malformed_calibration_manifest")
        entry["entry_type"] = "baseline_calibration"
        entry["status"] = "malformed_calibration_manifest"
        entry["manifest_path"] = str(manifest_path)
        entry["error"] = str(exc)
        return entry
    metrics = manifest.get("metrics") or {}
    tuning = manifest.get("baseline_tuning") or {}
    warnings = []
    if str(manifest.get("calibration_status", "")).startswith("blocked") or str(manifest.get("calibration_status", "")).startswith("diagnostic"):
        warnings.append(f"Calibration status is {manifest.get('calibration_status')}")
    present = [name for name in CALIBRATION_OUTPUT_NAMES if (run_dir / name).exists()]
    return {
        "entry_type": "baseline_calibration",
        "run_date": str(manifest.get("run_date") or run_dir.name),
        "run_id": str(manifest.get("calibration_run_id") or manifest.get("run_id") or f"baseline_calibration_{run_dir.name}"),
        "generated_at": str(manifest.get("generated_at") or ""),
        "status": str(manifest.get("calibration_status") or "unknown"),
        "currentness_status": "calibration",
        "season_sanity_status": "not_applicable",
        "leagues": [],
        "row_count": int(metrics.get("row_count") or 0),
        "calibration_status": str(manifest.get("calibration_status") or ""),
        "calibration_data_source": str(manifest.get("calibration_data_source") or manifest.get("data_source") or ""),
        "calibration_output_dir": str(manifest.get("calibration_output_dir") or run_dir),
        "calibration_config_hash": str(manifest.get("calibration_config_hash") or ""),
        "tuning_status": str(tuning.get("status") or "not_requested"),
        "tuning_recommendation": str(tuning.get("best_recommendation") or ""),
        "wdl_log_loss": metrics.get("wdl_log_loss"),
        "brier_score": metrics.get("brier_score"),
        "ou25_brier_score": metrics.get("over_under_2_5_brier_score"),
        "most_likely_score_hit_rate": metrics.get("most_likely_score_hit_rate"),
        "warnings_count": len(warnings),
        "warnings": warnings,
        "output_files_present": present,
        "manifest_path": str(manifest_path),
        "summary_path": str(run_dir / "baseline_calibration_summary.md") if (run_dir / "baseline_calibration_summary.md").exists() else "",
        "run_dir": str(run_dir),
        "error": "",
    }


def _historical_seed_entry(seed_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry = _empty_entry(seed_dir, "malformed_historical_seed_manifest")
        entry["entry_type"] = "historical_calibration_seed"
        entry["status"] = "malformed_historical_seed_manifest"
        entry["manifest_path"] = str(manifest_path)
        entry["error"] = str(exc)
        return entry
    present = [name for name in HISTORICAL_SEED_OUTPUT_NAMES if (seed_dir / name).exists()]
    matched = int(manifest.get("historical_matches_with_ratings_rows") or 0)
    status = "ready" if matched else "blocked_missing_matched_historical_rows"
    return {
        "entry_type": "historical_calibration_seed",
        "run_date": str(manifest.get("run_date") or seed_dir.parent.name),
        "run_id": str(manifest.get("run_id") or f"historical_seed_{seed_dir.parent.name}"),
        "generated_at": str(manifest.get("generated_at") or ""),
        "status": status,
        "currentness_status": "historical_seed",
        "season_sanity_status": "not_applicable",
        "leagues": [],
        "row_count": matched,
        "historical_rating_snapshot_rows": int(manifest.get("historical_rating_snapshot_rows") or 0),
        "historical_results_rows": int(manifest.get("historical_results_rows") or 0),
        "historical_matches_with_ratings_rows": matched,
        "warnings_count": 0 if matched else 1,
        "warnings": [] if matched else ["Historical seed did not produce matched result/rating rows."],
        "output_files_present": present,
        "manifest_path": str(manifest_path),
        "summary_path": str(seed_dir / "historical_seed_summary.md") if (seed_dir / "historical_seed_summary.md").exists() else "",
        "run_dir": str(seed_dir),
        "error": "",
    }


def _club_readiness_entry(run_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry = _empty_entry(run_dir, "malformed_league_readiness_manifest")
        entry["entry_type"] = "club_league_readiness"
        entry["status"] = "malformed_league_readiness_manifest"
        entry["manifest_path"] = str(manifest_path)
        entry["error"] = str(exc)
        return entry
    present = [name for name in CLUB_READINESS_OUTPUT_NAMES if (run_dir / name).exists()]
    return {
        "entry_type": "club_league_readiness",
        "run_date": str(manifest.get("as_of_date") or run_dir.parent.name),
        "run_id": str(manifest.get("run_id") or f"club_league_readiness_{run_dir.parent.name}"),
        "generated_at": str(manifest.get("generated_at") or ""),
        "status": str(manifest.get("status") or "unknown"),
        "currentness_status": "club_league_readiness",
        "season_sanity_status": "not_applicable",
        "leagues": list(manifest.get("leagues") or []),
        "row_count": 0,
        "warnings_count": 1 if str(manifest.get("status") or "").endswith("warnings") else 0,
        "warnings": ["League readiness has warnings; inspect by-league output."] if str(manifest.get("status") or "").endswith("warnings") else [],
        "output_files_present": present,
        "manifest_path": str(manifest_path),
        "summary_path": str(run_dir / "league_readiness_summary.md") if (run_dir / "league_readiness_summary.md").exists() else "",
        "run_dir": str(run_dir),
        "slate_type": "club_league_readiness",
        "error": "",
    }


def _grading_entry(run_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry = _empty_entry(run_dir, "malformed_grading_manifest")
        entry["entry_type"] = "current_result_grading"
        entry["status"] = "malformed_grading_manifest"
        entry["manifest_path"] = str(manifest_path)
        entry["error"] = str(exc)
        return entry
    metrics = manifest.get("metrics") or {}
    present = [name for name in GRADING_OUTPUT_NAMES if (run_dir / name).exists()]
    return {
        "entry_type": "current_result_grading",
        "run_date": str(manifest.get("run_date") or run_dir.parent.name),
        "run_id": str(manifest.get("run_id") or run_dir.name),
        "generated_at": str(manifest.get("generated_at") or ""),
        "status": str(manifest.get("status") or "unknown"),
        "currentness_status": "result_grading",
        "season_sanity_status": "not_applicable",
        "leagues": [],
        "row_count": int(metrics.get("graded_matches") or 0),
        "graded_matches": int(metrics.get("graded_matches") or 0),
        "exact_score_hit_rate": metrics.get("exact_score_hit_rate"),
        "top_3_score_hit_rate": metrics.get("top_3_score_hit_rate"),
        "top_5_score_hit_rate": metrics.get("top_5_score_hit_rate"),
        "actual_score_rank_average": metrics.get("actual_score_rank_average"),
        "total_goals_mae": metrics.get("total_goals_mae"),
        "ou25_brier_score": metrics.get("over_2_5_brier_score"),
        "btts_brier_score": metrics.get("btts_brier_score"),
        "warnings_count": 1 if manifest.get("warning") else 0,
        "warnings": [manifest["warning"]] if manifest.get("warning") else [],
        "output_files_present": present,
        "manifest_path": str(manifest_path),
        "summary_path": str(run_dir / "current_projection_grading_summary.md") if (run_dir / "current_projection_grading_summary.md").exists() else "",
        "run_dir": str(run_dir),
        "error": "",
        "slate_type": "current_result_grading",
    }


def _scoreline_diagnostics_entry(run_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry = _empty_entry(run_dir, "malformed_scoreline_diagnostics_manifest")
        entry["entry_type"] = "scoreline_diagnostics"
        entry["status"] = "malformed_scoreline_diagnostics_manifest"
        entry["manifest_path"] = str(manifest_path)
        entry["error"] = str(exc)
        return entry
    metrics = manifest.get("metrics") or {}
    present = [name for name in SCORELINE_DIAGNOSTIC_OUTPUT_NAMES if (run_dir / name).exists()]
    return {
        "entry_type": "scoreline_diagnostics",
        "run_date": str(manifest.get("run_date") or run_dir.parent.parent.name),
        "run_id": str(manifest.get("run_id") or run_dir.name),
        "generated_at": str(manifest.get("generated_at") or ""),
        "status": str(manifest.get("status") or "diagnostic_only"),
        "currentness_status": "scoreline_diagnostics",
        "season_sanity_status": "not_applicable",
        "leagues": [],
        "row_count": int(metrics.get("row_count") or 0),
        "exact_score_hit_rate": metrics.get("actual_score_hit_rate"),
        "top_3_score_hit_rate": metrics.get("top_3_correct_score_hit_rate"),
        "top_5_score_hit_rate": metrics.get("top_5_correct_score_hit_rate"),
        "actual_score_rank_average": metrics.get("actual_score_rank_average"),
        "total_goals_mae": metrics.get("total_goals_mae"),
        "ou25_brier_score": metrics.get("over_under_2_5_brier_score"),
        "btts_brier_score": metrics.get("btts_brier_score"),
        "warnings_count": 1 if "insufficient_rows" in (manifest.get("diagnostic_labels") or []) else 0,
        "warnings": list(manifest.get("diagnostic_labels") or []),
        "output_files_present": present,
        "manifest_path": str(manifest_path),
        "summary_path": str(run_dir / "scoreline_diagnostics_summary.md") if (run_dir / "scoreline_diagnostics_summary.md").exists() else "",
        "run_dir": str(run_dir),
        "error": "",
        "slate_type": "scoreline_diagnostics",
    }


def _iter_run_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for run_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda p: p.name, reverse=True):
        if not any(run_dir.iterdir()):
            entries.append(_empty_entry(run_dir, "empty_run_folder"))
            continue
        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.exists():
            entries.append(_empty_entry(run_dir, "missing_manifest"))
            continue
        entries.append(_manifest_entry(run_dir, manifest_path))
    return entries


def _iter_checkpoint_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not root.exists() or not root.is_dir():
        return entries
    for checkpoint_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda p: p.name, reverse=True):
        manifest_path = checkpoint_dir / "projection_checkpoint_manifest.json"
        if manifest_path.exists():
            entries.append(_checkpoint_entry(checkpoint_dir, manifest_path))
    return entries


def _iter_current_international_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not root.exists() or not root.is_dir():
        return entries
    for run_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda p: p.name, reverse=True):
        manifest_path = run_dir / "current_international_manifest.json"
        if manifest_path.exists():
            entries.append(_current_international_entry(run_dir, manifest_path))
    return entries


def _iter_calibration_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not root.exists() or not root.is_dir():
        return entries
    for manifest_path in sorted(root.rglob("calibration_manifest.json"), key=lambda p: str(p), reverse=True):
        entries.append(_calibration_entry(manifest_path.parent, manifest_path))
    for run_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda p: p.name, reverse=True):
        seed_manifest = run_dir / "historical_seed" / "historical_seed_manifest.json"
        if seed_manifest.exists():
            entries.append(_historical_seed_entry(run_dir / "historical_seed", seed_manifest))
    for manifest_path in sorted(root.glob("*/scoreline_diagnostics/*/scoreline_diagnostics_manifest.json"), key=lambda p: str(p), reverse=True):
        entries.append(_scoreline_diagnostics_entry(manifest_path.parent, manifest_path))
    return entries


def _iter_club_readiness_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not root.exists() or not root.is_dir():
        return entries
    for manifest_path in sorted(root.glob("*/league_readiness/league_readiness_manifest.json"), key=lambda p: str(p), reverse=True):
        entries.append(_club_readiness_entry(manifest_path.parent, manifest_path))
    return entries


def _iter_grading_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not root.exists() or not root.is_dir():
        return entries
    for manifest_path in sorted(root.glob("*/*/result_grading_manifest.json"), key=lambda p: str(p), reverse=True):
        entries.append(_grading_entry(manifest_path.parent, manifest_path))
    return entries


def build_run_index(runs_root: str | Path = "outputs/runs") -> list[dict[str, Any]]:
    root = Path(runs_root)
    if not root.exists() or not root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    run_roots = [root]
    if (root / "runs").exists() and root.name != "runs":
        run_roots = [root / "runs"]
    elif (
        (root / "projection_checkpoints").exists()
        or (root / "current_international").exists()
        or (root / "calibration").exists()
        or (root / "club").exists()
        or (root / "grading").exists()
        or root.name == "calibration"
        or root.name == "club"
        or root.name == "grading"
    ) and root.name != "runs":
        run_roots = []
    for run_root in run_roots:
        if run_root.exists() and run_root.is_dir():
            entries.extend(_iter_run_entries(run_root))

    checkpoint_root = root if root.name == "projection_checkpoints" else root / "projection_checkpoints"
    entries.extend(_iter_checkpoint_entries(checkpoint_root))
    current_international_root = root if root.name == "current_international" else root / "current_international"
    entries.extend(_iter_current_international_entries(current_international_root))
    calibration_root = root if root.name == "calibration" else root / "calibration"
    entries.extend(_iter_calibration_entries(calibration_root))
    club_root = root if root.name == "club" else root / "club"
    entries.extend(_iter_club_readiness_entries(club_root))
    grading_root = root if root.name == "grading" else root / "grading"
    entries.extend(_iter_grading_entries(grading_root))
    return sorted(entries, key=lambda item: (item.get("run_date", ""), item.get("generated_at", "")), reverse=True)


def format_run_index_table(entries: list[dict[str, Any]]) -> str:
    headers = ["date", "type", "status", "currentness", "rows", "warnings", "slate_type"]
    rows = [
        [
            item.get("run_date", ""),
            item.get("entry_type", "daily_run"),
            item.get("status", ""),
            item.get("currentness_status", ""),
            str(item.get("row_count", 0)),
            str(item.get("warnings_count", 0)),
            item.get("slate_type", ""),
        ]
        for item in entries
    ]
    if not rows:
        return "No runs found."
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, widths))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend("  ".join(value.ljust(width) for value, width in zip(row, widths)) for row in rows)
    return "\n".join(lines)
