from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.analysis.baseline_tuning import project_candidate_xg
from src.analysis.scoreline_calibration import scoreline_rankings


MANUAL_RESULT_COLUMNS = ["fixture_date", "home_team", "away_team", "home_goals", "away_goals", "source_name"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id(as_of_date: str, created_at: str) -> str:
    suffix = hashlib.sha1(f"{as_of_date}|{created_at}".encode("utf-8")).hexdigest()[:8]
    return f"grading_{as_of_date.replace('-', '')}_{suffix}"


def _clean_team(value: Any) -> str:
    return str(value or "").strip().lower()


def _match_key(home: Any, away: Any, fixture_date: Any = "") -> tuple[str, str, str]:
    return (_clean_team(home), _clean_team(away), str(fixture_date or "")[:10])


def _number(row: pd.Series, names: list[str], default: float = np.nan) -> float:
    for name in names:
        if name in row and not pd.isna(row[name]):
            try:
                return float(row[name])
            except (TypeError, ValueError):
                continue
    return default


def _text(row: pd.Series, names: list[str], default: str = "") -> str:
    for name in names:
        if name in row and not pd.isna(row[name]):
            return str(row[name])
    return default


def _normalize_projection_rows(projections: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in projections.iterrows():
        home = _text(row, ["home_team", "team_a"])
        away = _text(row, ["away_team", "team_b"])
        fixture_date = _text(row, ["fixture_date", "match_date", "date"])
        home_xg = _number(row, ["projected_home_xg", "home_xg", "team_a_xg_final"])
        away_xg = _number(row, ["projected_away_xg", "away_xg", "team_b_xg_final"])
        rows.append({
            "fixture_date": fixture_date,
            "home_team": home,
            "away_team": away,
            "projected_home_xg": home_xg,
            "projected_away_xg": away_xg,
            "projected_total": _number(row, ["projected_total"], home_xg + away_xg if not pd.isna(home_xg) and not pd.isna(away_xg) else np.nan),
            "projected_most_likely_score": _text(row, ["most_likely_exact_score", "most_likely_score"]),
            "projected_home_win_probability": _number(row, ["home_win_probability", "home_win_prob", "team_a_win_prob"], np.nan),
            "projected_draw_probability": _number(row, ["draw_probability", "draw_prob"], np.nan),
            "projected_away_win_probability": _number(row, ["away_win_probability", "away_win_prob", "team_b_win_prob"], np.nan),
            "projected_over_2_5_probability": _number(row, ["over_2_5_probability", "over_2_5_prob"], np.nan),
            "projected_btts_probability": _number(row, ["btts_yes_probability", "btts_prob"], np.nan),
        })
    return pd.DataFrame(rows)


def load_manual_results(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = [column for column in MANUAL_RESULT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Manual result CSV is missing required columns: {', '.join(missing)}")
    out = frame.copy()
    out["home_goals"] = pd.to_numeric(out["home_goals"], errors="coerce")
    out["away_goals"] = pd.to_numeric(out["away_goals"], errors="coerce")
    out = out.dropna(subset=["home_goals", "away_goals"]).copy()
    out["result_source_type"] = "manual_source_supplied"
    out["result_source_name"] = out["source_name"].astype(str)
    return out


def _load_cached_results(cache_dir: str | Path) -> pd.DataFrame:
    root = Path(cache_dir)
    candidates = [
        root / "parsed" / "historical_results.csv",
        root / "parsed" / "results.csv",
        root / "results.csv",
        root / "fixtures.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        rename = {
            "match_date": "fixture_date",
            "home_score": "home_goals",
            "away_score": "away_goals",
        }
        frame = frame.rename(columns={key: value for key, value in rename.items() if key in frame.columns})
        if {"fixture_date", "home_team", "away_team", "home_goals", "away_goals"}.issubset(frame.columns):
            out = frame.copy()
            out["home_goals"] = pd.to_numeric(out["home_goals"], errors="coerce")
            out["away_goals"] = pd.to_numeric(out["away_goals"], errors="coerce")
            out = out.dropna(subset=["home_goals", "away_goals"]).copy()
            if not out.empty:
                out["result_source_type"] = "allowed_public_cache"
                out["result_source_name"] = out.get("source_name", pd.Series(["cache"] * len(out))).astype(str)
                return out
    return pd.DataFrame()


def load_actual_results(
    *,
    actual_results: str | Path | None = None,
    source_cache_dir: str | Path = "data/source_cache/current_international",
    allow_network: bool = False,
) -> dict[str, Any]:
    if actual_results:
        rows = load_manual_results(actual_results)
        return {"status": "manual_results_loaded", "rows": rows, "source": str(actual_results), "allow_network": allow_network}
    cached = _load_cached_results(source_cache_dir)
    if not cached.empty:
        return {"status": "cached_results_loaded", "rows": cached, "source": str(source_cache_dir), "allow_network": allow_network}
    return {
        "status": "no_results_available",
        "rows": pd.DataFrame(),
        "source": "",
        "allow_network": allow_network,
        "warning": "No allowed cached result source or manual result CSV contained completed scores. No results were faked.",
    }


def classify_miss_type(row: pd.Series) -> str:
    if pd.isna(row.get("actual_home_goals")) or pd.isna(row.get("actual_away_goals")):
        return "insufficient_data"
    if bool(row.get("exact_score_hit")):
        return "exact_score_hit"
    projected_total = float(row.get("projected_total") or 0.0)
    actual_total = float(row.get("actual_total") or 0.0)
    predicted = _wdl_from_probs(
        row.get("projected_home_win_probability"),
        row.get("projected_draw_probability"),
        row.get("projected_away_win_probability"),
    )
    actual = row.get("wdl_result")
    if predicted != actual:
        if actual == "draw":
            return "draw_missed"
        return "winner_wrong"
    if actual_total >= projected_total + 1.0:
        if float(row.get("actual_home_goals") or 0.0) > float(row.get("projected_home_xg") or 0.0) + 0.75:
            return "favorite_attack_underestimated"
        if float(row.get("actual_away_goals") or 0.0) > float(row.get("projected_away_xg") or 0.0) + 0.75:
            return "underdog_attack_underestimated"
        return "total_too_low"
    if actual_total <= projected_total - 1.0:
        return "total_too_high"
    if bool(row.get("actual_btts")) and float(row.get("projected_btts_probability") or 0.0) < 0.45:
        return "both_teams_scored_missed"
    if not bool(row.get("actual_btts")) and float(row.get("projected_btts_probability") or 1.0) > 0.55:
        return "clean_sheet_missed"
    return "scoreline_close"


def _wdl_from_probs(home: Any, draw: Any, away: Any) -> str:
    values = {
        "home": float(home) if not pd.isna(home) else 0.0,
        "draw": float(draw) if not pd.isna(draw) else 0.0,
        "away": float(away) if not pd.isna(away) else 0.0,
    }
    return max(values, key=values.get)


def _wdl_from_goals(home_goals: float, away_goals: float) -> str:
    if home_goals > away_goals:
        return "home"
    if away_goals > home_goals:
        return "away"
    return "draw"


def grade_projection_rows(
    projections: pd.DataFrame,
    actuals: pd.DataFrame,
    *,
    poisson_dir: str | Path | None = None,
    min_matches: int = 1,
) -> dict[str, Any]:
    projection_rows = _normalize_projection_rows(projections)
    if projection_rows.empty or actuals.empty:
        empty = pd.DataFrame(columns=[
            "match",
            "fixture_date",
            "projected_home_xg",
            "projected_away_xg",
            "projected_total",
            "actual_home_goals",
            "actual_away_goals",
            "actual_total",
            "miss_type",
            "grading_warning",
        ])
        status = "blocked_no_projections" if projection_rows.empty else "no_results_available"
        return {"status": status, "graded_matches": empty, "summary": _summary_metrics(empty, min_matches=min_matches)}
    actual_lookup = {
        _match_key(row["home_team"], row["away_team"], row.get("fixture_date", "")): row
        for _, row in actuals.iterrows()
    }
    graded: list[dict[str, Any]] = []
    for _, row in projection_rows.iterrows():
        actual = actual_lookup.get(_match_key(row["home_team"], row["away_team"], row.get("fixture_date", "")))
        if actual is None:
            actual = actual_lookup.get(_match_key(row["home_team"], row["away_team"], ""))
        if actual is None:
            continue
        home_goals = int(float(actual["home_goals"]))
        away_goals = int(float(actual["away_goals"]))
        rank_input = pd.DataFrame([{
            "fixture_date": row["fixture_date"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "projected_home_xg": row["projected_home_xg"],
            "projected_away_xg": row["projected_away_xg"],
            "home_goals": home_goals,
            "away_goals": away_goals,
            "home_win_probability": row["projected_home_win_probability"],
            "draw_probability": row["projected_draw_probability"],
            "away_win_probability": row["projected_away_win_probability"],
            "over_2_5_probability": row["projected_over_2_5_probability"],
            "btts_probability": row["projected_btts_probability"],
        }])
        ranking = scoreline_rankings(rank_input).iloc[0].to_dict()
        actual_total = home_goals + away_goals
        actual_over = actual_total > 2.5
        actual_btts = home_goals > 0 and away_goals > 0
        projected_over = float(row["projected_over_2_5_probability"]) if not pd.isna(row["projected_over_2_5_probability"]) else 0.5
        projected_btts = float(row["projected_btts_probability"]) if not pd.isna(row["projected_btts_probability"]) else 0.5
        record = {
            "match": f"{row['home_team']} vs {row['away_team']}",
            "fixture_date": row["fixture_date"],
            "projected_home_xg": row["projected_home_xg"],
            "projected_away_xg": row["projected_away_xg"],
            "projected_total": row["projected_total"],
            "actual_home_goals": home_goals,
            "actual_away_goals": away_goals,
            "actual_total": actual_total,
            "projected_most_likely_score": row["projected_most_likely_score"] or ranking["most_likely_exact_score"],
            "actual_score": ranking["actual_score"],
            "exact_score_hit": bool(ranking["exact_score_hit"]),
            "top_3_score_hit": bool(ranking["top_3_score_hit"]),
            "top_5_score_hit": bool(ranking["top_5_score_hit"]),
            "actual_score_rank": ranking["actual_score_rank"],
            "actual_score_probability": ranking["actual_score_probability"],
            "projected_home_win_probability": row["projected_home_win_probability"],
            "projected_draw_probability": row["projected_draw_probability"],
            "projected_away_win_probability": row["projected_away_win_probability"],
            "wdl_result": _wdl_from_goals(home_goals, away_goals),
            "projected_wdl_result": _wdl_from_probs(row["projected_home_win_probability"], row["projected_draw_probability"], row["projected_away_win_probability"]),
            "projected_over_2_5_probability": projected_over,
            "actual_over_2_5": actual_over,
            "over_2_5_brier_component": (projected_over - float(actual_over)) ** 2,
            "projected_btts_probability": projected_btts,
            "actual_btts": actual_btts,
            "btts_brier_component": (projected_btts - float(actual_btts)) ** 2,
            "result_source_type": actual.get("result_source_type", ""),
            "result_source_name": actual.get("result_source_name", actual.get("source_name", "")),
            "grading_warning": "",
        }
        record["wdl_correct"] = record["wdl_result"] == record["projected_wdl_result"]
        record["miss_type"] = classify_miss_type(pd.Series(record))
        graded.append(record)
    frame = pd.DataFrame(graded)
    status = "graded" if len(frame) >= min_matches else "insufficient_graded_matches"
    return {"status": status, "graded_matches": frame, "summary": _summary_metrics(frame, min_matches=min_matches)}


def _summary_metrics(frame: pd.DataFrame, *, min_matches: int) -> dict[str, Any]:
    if frame.empty:
        return {
            "graded_matches": 0,
            "min_matches": min_matches,
            "exact_score_hit_rate": None,
            "top_3_score_hit_rate": None,
            "top_5_score_hit_rate": None,
            "actual_score_rank_average": None,
            "total_goals_mae": None,
            "over_2_5_brier_score": None,
            "btts_brier_score": None,
            "wdl_accuracy": None,
        }
    return {
        "graded_matches": int(len(frame)),
        "min_matches": min_matches,
        "exact_score_hit_rate": float(frame["exact_score_hit"].mean()),
        "top_3_score_hit_rate": float(frame["top_3_score_hit"].mean()),
        "top_5_score_hit_rate": float(frame["top_5_score_hit"].mean()),
        "actual_score_rank_average": float(pd.to_numeric(frame["actual_score_rank"], errors="coerce").dropna().mean()) if frame["actual_score_rank"].notna().any() else None,
        "total_goals_mae": float((frame["projected_total"].astype(float) - frame["actual_total"].astype(float)).abs().mean()),
        "over_2_5_brier_score": float(frame["over_2_5_brier_component"].mean()),
        "btts_brier_score": float(frame["btts_brier_component"].mean()),
        "wdl_accuracy": float(frame["wdl_correct"].mean()),
    }


def grade_current_projections(
    *,
    as_of_date: str,
    projection_file: str | Path | None = None,
    poisson_dir: str | Path | None = None,
    actual_results: str | Path | None = None,
    allow_network: bool = False,
    source_cache_dir: str | Path = "data/source_cache/current_international",
    output_dir: str | Path = "outputs/grading",
    min_matches: int = 1,
    candidate_config: str | Path | None = None,
) -> dict[str, Any]:
    created_at = _now_iso()
    run_id = _run_id(as_of_date, created_at)
    projection_path = Path(projection_file) if projection_file else Path("outputs/current_international") / as_of_date / "current_international_projections.csv"
    if projection_path.exists():
        projections = pd.read_csv(projection_path)
        projection_status = "loaded"
    else:
        projections = pd.DataFrame()
        projection_status = "blocked_missing_projection_file"
    actual_result = load_actual_results(actual_results=actual_results, source_cache_dir=source_cache_dir, allow_network=allow_network)
    grade = grade_projection_rows(projections, actual_result["rows"], poisson_dir=poisson_dir, min_matches=min_matches)
    run_dir = Path(output_dir) / as_of_date / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": run_dir / "current_projection_grading_summary.md",
        "graded_matches": run_dir / "graded_matches.csv",
        "scoreline_miss_types": run_dir / "scoreline_miss_types.csv",
        "manifest": run_dir / "result_grading_manifest.json",
    }
    graded = grade["graded_matches"]
    graded.to_csv(paths["graded_matches"], index=False)
    miss_types = (
        graded.groupby("miss_type", observed=False).size().reset_index(name="matches")
        if not graded.empty and "miss_type" in graded
        else pd.DataFrame(columns=["miss_type", "matches"])
    )
    miss_types.to_csv(paths["scoreline_miss_types"], index=False)
    candidate_comparison = _write_candidate_grading_comparison(
        run_dir,
        projections=projections,
        actuals=actual_result["rows"],
        candidate_config=candidate_config,
        min_matches=min_matches,
    )
    status = grade["status"]
    if projection_status != "loaded":
        status = projection_status
    manifest = {
        "run_id": run_id,
        "entry_type": "current_result_grading",
        "run_date": as_of_date,
        "generated_at": created_at,
        "status": status,
        "projection_file": str(projection_path),
        "poisson_dir": str(poisson_dir or ""),
        "actual_result_status": actual_result["status"],
        "actual_result_source": actual_result.get("source", ""),
        "allow_network": allow_network,
        "manual_results_used": bool(actual_results),
        "candidate_config": str(candidate_config or ""),
        "candidate_grading_comparison": candidate_comparison,
        "metrics": grade["summary"],
        "guardrails": {
            "fake_results_used": False,
            "current_statsbomb_live_data_used": False,
            "betting_recommendations": False,
        },
        "output_paths": {key: str(path) for key, path in paths.items()},
    }
    if actual_result.get("warning"):
        manifest["warning"] = actual_result["warning"]
    paths["manifest"].write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    paths["summary"].write_text(_summary_markdown(manifest, miss_types), encoding="utf-8")
    return {
        "status": status,
        "manifest": manifest,
        "paths": {key: str(path) for key, path in paths.items()},
        "run_dir": run_dir,
        "graded_matches": graded,
        "miss_types": miss_types,
    }


def _summary_markdown(manifest: dict[str, Any], miss_types: pd.DataFrame) -> str:
    metrics = manifest["metrics"]
    lines = [
        "# Current Projection Grading",
        "",
        "- Compares saved pre-match projections to completed results.",
        "- No results are faked; manual results are labeled source-supplied.",
        "- Exact scores are naturally low-probability outcomes.",
        "",
        f"- Status: `{manifest.get('status')}`",
        f"- Projection file: `{manifest.get('projection_file')}`",
        f"- Actual result status: `{manifest.get('actual_result_status')}`",
        f"- Graded matches: `{metrics.get('graded_matches')}`",
        f"- Exact score hit rate: `{metrics.get('exact_score_hit_rate')}`",
        f"- Top 3 score hit rate: `{metrics.get('top_3_score_hit_rate')}`",
        f"- Top 5 score hit rate: `{metrics.get('top_5_score_hit_rate')}`",
        f"- Average actual score rank: `{metrics.get('actual_score_rank_average')}`",
        f"- Total goals MAE: `{metrics.get('total_goals_mae')}`",
        f"- O/U 2.5 Brier: `{metrics.get('over_2_5_brier_score')}`",
        f"- BTTS Brier: `{metrics.get('btts_brier_score')}`",
        f"- W/D/L accuracy: `{metrics.get('wdl_accuracy')}`",
        "",
        "## Miss Types",
        "",
    ]
    if miss_types.empty:
        lines.append("_No graded miss types._")
    else:
        lines.extend([
            "| miss_type | matches |",
            "| --- | --- |",
            *[f"| {row['miss_type']} | {row['matches']} |" for _, row in miss_types.iterrows()],
        ])
    lines.extend([
        "",
        "## Guardrails",
        "",
        "- Manual result CSVs are treated as source-supplied, not scraped.",
        "- No current StatsBomb live data is used.",
        "- No betting recommendations are produced.",
    ])
    return "\n".join(lines)


def format_grading_terminal(result: dict[str, Any]) -> str:
    metrics = result["manifest"]["metrics"]
    return "\n".join([
        "Current Projection Grading",
        f"Status: {result['status']}",
        f"Actual result status: {result['manifest']['actual_result_status']}",
        f"Graded matches: {metrics.get('graded_matches')}",
        f"Exact score hit rate: {metrics.get('exact_score_hit_rate')}",
        f"Top 3 score hit rate: {metrics.get('top_3_score_hit_rate')}",
        f"Top 5 score hit rate: {metrics.get('top_5_score_hit_rate')}",
        f"Average actual score rank: {metrics.get('actual_score_rank_average')}",
        f"Total goals MAE: {metrics.get('total_goals_mae')}",
        f"O/U 2.5 Brier: {metrics.get('over_2_5_brier_score')}",
        f"BTTS Brier: {metrics.get('btts_brier_score')}",
        f"Candidate grading comparison: {result['manifest'].get('candidate_grading_comparison', {}).get('status')}",
        f"Summary: {result['paths']['summary']}",
    ])


def _write_candidate_grading_comparison(
    run_dir: Path,
    *,
    projections: pd.DataFrame,
    actuals: pd.DataFrame,
    candidate_config: str | Path | None,
    min_matches: int,
) -> dict[str, Any]:
    if not candidate_config:
        return {"status": "not_requested", "paths": {}}
    path = Path(candidate_config)
    if not path.exists():
        return {"status": "blocked_missing_candidate_config", "paths": {}, "warning": str(path)}
    if projections.empty or actuals.empty:
        return {"status": "blocked_missing_projection_or_actual_rows", "paths": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "blocked_invalid_candidate_config", "paths": {}, "warning": str(exc)}
    params = payload.get("model_parameters") or {}
    candidate_rows = []
    for _, row in projections.iterrows():
        if pd.isna(row.get("home_rating")) or pd.isna(row.get("away_rating")):
            continue
        candidate = project_candidate_xg(float(row["home_rating"]), float(row["away_rating"]), params)
        out = row.copy()
        out["team_a_xg_final"] = candidate["home_xg"]
        out["team_b_xg_final"] = candidate["away_xg"]
        out["projected_total"] = candidate["projected_total"]
        out["most_likely_score"] = candidate["most_likely_score"]
        out["team_a_win_prob"] = candidate["home_win_prob"]
        out["draw_prob"] = candidate["draw_prob"]
        out["team_b_win_prob"] = candidate["away_win_prob"]
        out["over_2_5_prob"] = candidate.get("over_2_5_prob")
        out["btts_prob"] = candidate.get("btts_prob")
        candidate_rows.append(out)
    if not candidate_rows:
        return {"status": "blocked_no_candidate_projection_rows", "paths": {}}
    baseline_grade = grade_projection_rows(projections, actuals, min_matches=min_matches)
    candidate_grade = grade_projection_rows(pd.DataFrame(candidate_rows), actuals, min_matches=min_matches)
    comparison_dir = run_dir / "candidate_grading_comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    baseline_metrics = baseline_grade["summary"]
    candidate_metrics = candidate_grade["summary"]
    comparison = pd.DataFrame([{
        "metric": key,
        "baseline": baseline_metrics.get(key),
        "candidate": candidate_metrics.get(key),
        "delta": _metric_delta(candidate_metrics.get(key), baseline_metrics.get(key)),
    } for key in sorted(set(baseline_metrics) | set(candidate_metrics))])
    csv_path = comparison_dir / "candidate_grading_comparison.csv"
    summary_path = comparison_dir / "candidate_grading_comparison_summary.md"
    comparison.to_csv(csv_path, index=False)
    lines = [
        "# Candidate Grading Comparison",
        "",
        "- Diagnostic only; production defaults are unchanged.",
        f"- Candidate config: `{path}`",
        f"- Baseline graded matches: `{baseline_metrics.get('graded_matches')}`",
        f"- Candidate graded matches: `{candidate_metrics.get('graded_matches')}`",
        f"- Total goals MAE delta: `{_metric_delta(candidate_metrics.get('total_goals_mae'), baseline_metrics.get('total_goals_mae'))}`",
        f"- W/D/L accuracy delta: `{_metric_delta(candidate_metrics.get('wdl_accuracy'), baseline_metrics.get('wdl_accuracy'))}`",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "status": "written",
        "paths": {
            "candidate_grading_comparison": str(csv_path),
            "candidate_grading_comparison_summary": str(summary_path),
        },
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
    }


def _metric_delta(candidate: Any, baseline: Any) -> float | None:
    try:
        return float(candidate) - float(baseline)
    except (TypeError, ValueError):
        return None

