from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.analysis.poisson_output import excel_safe_score_label, write_poisson_outputs


CHECKPOINT_OUTPUT_FILES = (
    "projection_checkpoint_summary.md",
    "projection_checkpoint_rows.csv",
    "projection_checkpoint_flags.csv",
    "projection_checkpoint_manifest.json",
)

SAMPLE_FIXTURE_WARNING = "Sample fixture data only. Do not treat this as a real current matchup."

RATING_ONLY_WARNING_TEXT = "rating-only"
STYLE_OVERCLAIM_TERMS = (
    "style-aware projection ready",
    "style adjustment applied",
    "style edge",
    "style advantage",
    "matchup style advantage",
)
ACTION_LANGUAGE_TERMS = (
    "best bet",
    "betting pick",
    "recommended bet",
    "wager",
    "stake",
    "lo" + "ck of",
    "must play",
    "action recommendation",
)
ACTION_LANGUAGE_DISCLAIMERS = (
    "no betting",
    "not a betting",
    "not betting",
    "no wagering",
    "not wagering",
    "not a wager",
    "no picks",
    "not a pick",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_date(as_of_date: str | None) -> str:
    return as_of_date or date.today().isoformat()


def _read_projection_file(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    return frame.fillna("")


def _first_value(row: pd.Series, names: list[str], default: Any = "") -> Any:
    for name in names:
        if name in row.index:
            value = row.get(name)
            if value != "":
                return value
    return default


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "available"}


def _row_text(row: pd.Series) -> str:
    return " | ".join(str(value) for value in row.to_dict().values() if value != "").lower()


def _dedupe_warning_text(*values: Any) -> str:
    warnings: list[str] = []
    for value in values:
        for part in str(value or "").replace("\n", " | ").split("|"):
            text = part.strip()
            if text and text not in warnings:
                warnings.append(text)
    return " | ".join(warnings)


def _contains_action_language(text: str) -> str:
    if any(disclaimer in text for disclaimer in ACTION_LANGUAGE_DISCLAIMERS):
        return ""
    for term in ACTION_LANGUAGE_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", text):
            return term
    return ""


def _contains_style_overclaim(text: str) -> bool:
    if "not style advantages" in text or "not a style advantage" in text:
        text = text.replace("not style advantages", "").replace("not a style advantage", "")
    if "no current xg/style claims" in text:
        text = text.replace("no current xg/style claims", "")
    return any(term in text for term in STYLE_OVERCLAIM_TERMS)


def _has_rating_only_warning(text: str) -> bool:
    return any(term in text for term in [
        "rating-only",
        "rating_only",
        "baseline score projection based on fixture + rating support only",
    ])


def _projection_side_names(row: pd.Series) -> tuple[str, str]:
    team_a = str(_first_value(row, ["team_a", "home_team", "home", "projected_home_team"], ""))
    team_b = str(_first_value(row, ["team_b", "away_team", "away", "projected_away_team"], ""))
    return team_a, team_b


def _safe_score_label(value: Any) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", text)
    if match:
        return excel_safe_score_label(match.group(1), match.group(2))
    return text


def normalize_projection_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        team_a, team_b = _projection_side_names(row)
        home_xg = _to_float(_first_value(row, ["projected_home_xg", "team_a_xg_final", "home_xg", "home_expected_goals"]))
        away_xg = _to_float(_first_value(row, ["projected_away_xg", "team_b_xg_final", "away_xg", "away_expected_goals"]))
        total = _to_float(_first_value(row, ["projected_total", "total_goals", "projected_goals_total"]))
        home_prob = _to_float(_first_value(row, ["home_win_probability", "team_a_win_prob", "home_win_prob"]))
        draw_prob = _to_float(_first_value(row, ["draw_probability", "draw_prob"]))
        away_prob = _to_float(_first_value(row, ["away_win_probability", "team_b_win_prob", "away_win_prob"]))
        style_inputs_available = _to_bool(_first_value(row, ["style_inputs_available"], False))
        is_sample_data = _to_bool(_first_value(row, ["is_sample_data"], False))
        source_tier = str(_first_value(row, ["source_tier"], "sample" if is_sample_data else "manual" if str(_first_value(row, ["reliability_status"], "")).lower() == "manual_fallback" else "real"))
        warnings_text = _dedupe_warning_text(*[
            _first_value(row, [name], "")
            for name in [
                "primary_warning",
                "rating_only_warning",
                "style_inputs_warning",
                "rating_warning",
                "style_warning",
                "source_warning",
                "guardrail_flags",
                "warnings",
                "risk_flags",
                "international_context_warnings",
                "current_source_warnings",
                "phase22_guardrails",
            ]
            if name in row.index
        ])
        rows.append({
            "source_row_index": index,
            "team_a": team_a,
            "team_b": team_b,
            "match_date": _first_value(row, ["match_date", "date"], ""),
            "projection_profile": _first_value(row, ["projection_profile"], ""),
            "baseline_mode_used": _first_value(row, ["baseline_mode_used", "baseline_mode"], ""),
            "projected_home_xg": home_xg,
            "projected_away_xg": away_xg,
            "projected_total": total,
            "home_win_probability": home_prob,
            "draw_probability": draw_prob,
            "away_win_probability": away_prob,
            "probability_sum": (
                round(home_prob + draw_prob + away_prob, 6)
                if home_prob is not None and draw_prob is not None and away_prob is not None
                else None
            ),
            "most_likely_score": _safe_score_label(_first_value(row, ["most_likely_score"], "")),
            "confidence_score": _to_float(_first_value(row, ["confidence_score"])),
            "confidence_label": _first_value(row, ["confidence_label"], ""),
            "data_mode": _first_value(row, ["data_mode", "current_fixture_data_mode"], ""),
            "data_support_level": _first_value(row, ["data_support_level"], ""),
            "rating_status": _first_value(row, ["rating_status"], ""),
            "reliability_status": _first_value(row, ["reliability_status"], ""),
            "source_tier": source_tier,
            "is_sample_data": is_sample_data,
            "style_inputs_available": style_inputs_available,
            "primary_warning": _first_value(row, ["primary_warning"], ""),
            "style_inputs_warning": _first_value(row, ["style_inputs_warning"], ""),
            "rating_only_warning": _first_value(row, ["rating_only_warning"], ""),
            "rating_warning": _first_value(row, ["rating_warning"], ""),
            "style_warning": _first_value(row, ["style_warning", "style_inputs_warning"], ""),
            "source_warning": _first_value(row, ["source_warning"], ""),
            "guardrail_flags": _first_value(row, ["guardrail_flags", "phase22_guardrails"], ""),
            "fixture_resolution_status": _first_value(row, ["fixture_resolution_status"], ""),
            "projection_eligible": _to_bool(_first_value(row, ["projection_eligible"], True)),
            "projection_skip_reason": _first_value(row, ["projection_skip_reason"], ""),
            "fixture_date": _first_value(row, ["fixture_date", "match_date", "date"], ""),
            "kickoff_time": _first_value(row, ["kickoff_time"], ""),
            "fixture_temporal_status": _first_value(row, ["fixture_temporal_status"], ""),
            "is_current_slate": _to_bool(_first_value(row, ["is_current_slate"], False)),
            "slate_window_status": _first_value(row, ["slate_window_status"], ""),
            "slate_skip_reason": _first_value(row, ["slate_skip_reason"], ""),
            "slate_window": _first_value(row, ["slate_window"], ""),
            "selected_by_slate_filter": _to_bool(_first_value(row, ["selected_by_slate_filter"], False)),
            "fixture_key": _first_value(row, ["fixture_key"], ""),
            "dedupe_match_key": _first_value(row, ["dedupe_match_key"], ""),
            "deduplication_status": _first_value(row, ["deduplication_status"], ""),
            "primary_source": _first_value(row, ["primary_source", "source_fixture_name"], ""),
            "duplicate_sources": _first_value(row, ["duplicate_sources"], ""),
            "dedupe_time_comparison": _first_value(row, ["dedupe_time_comparison"], ""),
            "dedupe_time_delta_minutes": _to_float(_first_value(row, ["dedupe_time_delta_minutes"], "")),
            "kickoff_time_normalized": _first_value(row, ["kickoff_time_normalized"], ""),
            "kickoff_timezone_status": _first_value(row, ["kickoff_timezone_status"], ""),
            "source_priority_score": _to_float(_first_value(row, ["source_priority_score"], "")),
            "warnings_text": warnings_text,
        })
    return pd.DataFrame(rows)


def _is_rating_only(row: pd.Series) -> bool:
    text = " ".join(str(row.get(name, "")) for name in [
        "baseline_mode_used",
        "data_mode",
        "data_support_level",
        "reliability_status",
        "warnings_text",
    ]).lower()
    return any(term in text for term in ["rating_only", "rating-only", "fixture_rating", "fixture-only", "fixture_only"])


def _high_confidence(row: pd.Series) -> bool:
    label = str(row.get("confidence_label", "")).lower()
    score = _to_float(row.get("confidence_score"))
    return label == "high" or (score is not None and score >= 70)


def _add_flag(flags: list[dict[str, Any]], row: pd.Series, flag_type: str, message: str, severity: str = "warning") -> None:
    flags.append({
        "source_row_index": int(row.get("source_row_index", -1)),
        "team_a": row.get("team_a", ""),
        "team_b": row.get("team_b", ""),
        "flag_type": flag_type,
        "severity": severity,
        "message": message,
    })


def analyze_projection_rows(frame: pd.DataFrame) -> dict[str, Any]:
    normalized = normalize_projection_rows(frame)
    flags: list[dict[str, Any]] = []
    if normalized.empty:
        flags.append({
            "source_row_index": -1,
            "team_a": "",
            "team_b": "",
            "flag_type": "no_projection_rows",
            "severity": "warning",
            "message": "No real current fixture source available. Provide --manual-matchups or run with --allow-sample-data for demo output.",
        })
    for _, row in normalized.iterrows():
        total = _to_float(row.get("projected_total"))
        home_xg = _to_float(row.get("projected_home_xg"))
        away_xg = _to_float(row.get("projected_away_xg"))
        home_prob = _to_float(row.get("home_win_probability"))
        draw_prob = _to_float(row.get("draw_probability"))
        away_prob = _to_float(row.get("away_win_probability"))
        text = _row_text(row)

        if total is None:
            _add_flag(flags, row, "missing_projected_total", "Projected total is missing.")
        elif total < 1.0 or total > 5.0:
            _add_flag(flags, row, "projected_total_out_of_range", f"Projected total {total:.2f} is outside the 1.0 to 5.0 sanity band.")
        if home_xg is not None and home_xg < 0:
            _add_flag(flags, row, "negative_projected_home_xg", "Projected home/team A xG is negative.")
        if away_xg is not None and away_xg < 0:
            _add_flag(flags, row, "negative_projected_away_xg", "Projected away/team B xG is negative.")
        if home_prob is None or draw_prob is None or away_prob is None:
            _add_flag(flags, row, "missing_wdl_probabilities", "One or more W/D/L probabilities are missing.")
        else:
            probability_sum = home_prob + draw_prob + away_prob
            if abs(probability_sum - 1.0) > 0.03:
                _add_flag(flags, row, "wdl_probability_sum_off", f"W/D/L probabilities sum to {probability_sum:.3f}, not close to 1.0.")
        if not row.get("most_likely_score"):
            _add_flag(flags, row, "missing_most_likely_score", "Most likely exact score is missing.")
        if _high_confidence(row) and _is_rating_only(row):
            _add_flag(flags, row, "high_confidence_low_support", "High confidence is paired with rating-only or fixture-only support.")
        if not row.get("style_inputs_available") and _contains_style_overclaim(text):
            _add_flag(flags, row, "style_overclaim", "Row uses style-aware language while style_inputs_available is false.")
        rating_warning_text = f"{row.get('rating_only_warning', '')} | {row.get('warnings_text', '')}".lower()
        if _is_rating_only(row) and not _has_rating_only_warning(rating_warning_text):
            _add_flag(flags, row, "missing_rating_only_warning", "Rating-only/fixture-rating projection is missing a clear rating-only warning.")
        action_term = _contains_action_language(text)
        if action_term:
            _add_flag(flags, row, "betting_or_action_language", f"Action language found: {action_term}.")
        if row.get("is_sample_data"):
            _add_flag(flags, row, "sample_demo_row", SAMPLE_FIXTURE_WARNING)

    flags_frame = pd.DataFrame(flags, columns=["source_row_index", "team_a", "team_b", "flag_type", "severity", "message"])
    status = "pass"
    if not normalized.empty and not flags_frame.empty:
        status = "warning"
    elif normalized.empty:
        status = "warning"

    summary = _summarize_checkpoint(normalized, flags_frame, status)
    return {"rows": normalized, "flags": flags_frame, "summary": summary}


def _counter_dict(values: pd.Series) -> dict[str, int]:
    cleaned = [str(value) if str(value) else "missing" for value in values.tolist()]
    return dict(Counter(cleaned))


def _summarize_checkpoint(rows: pd.DataFrame, flags: pd.DataFrame, status: str) -> dict[str, Any]:
    totals = pd.to_numeric(rows.get("projected_total", pd.Series(dtype=float)), errors="coerce").dropna()
    scores = [str(value) for value in rows.get("most_likely_score", pd.Series(dtype=str)).tolist() if str(value)]
    most_common_score = Counter(scores).most_common(1)[0][0] if scores else "missing"
    data_support_counts = _counter_dict(rows.get("data_support_level", pd.Series(dtype=str))) if not rows.empty else {}
    confidence_counts = _counter_dict(rows.get("confidence_label", pd.Series(dtype=str))) if not rows.empty else {}
    style_count = int(rows.get("style_inputs_available", pd.Series(dtype=bool)).astype(bool).sum()) if not rows.empty else 0
    missing_data_count = int(flags["flag_type"].isin([
        "missing_projected_total",
        "missing_wdl_probabilities",
        "missing_most_likely_score",
    ]).sum()) if not flags.empty else 0
    rating_only_count = int(rows.apply(_is_rating_only, axis=1).sum()) if not rows.empty else 0
    sample_count = int(rows.get("is_sample_data", pd.Series(dtype=bool)).astype(bool).sum()) if not rows.empty else 0
    manual_count = int((rows.get("source_tier", pd.Series(dtype=str)).astype(str) == "manual").sum()) if not rows.empty else 0
    real_count = int(len(rows) - sample_count - manual_count)
    if sample_count:
        status = "warning"
    return {
        "status": status,
        "rows_reviewed": int(len(rows)),
        "real_rows_reviewed": real_count,
        "manual_rows_reviewed": manual_count,
        "sample_rows_reviewed": sample_count,
        "average_projected_total": round(float(totals.mean()), 3) if not totals.empty else None,
        "min_projected_total": round(float(totals.min()), 3) if not totals.empty else None,
        "max_projected_total": round(float(totals.max()), 3) if not totals.empty else None,
        "most_common_likely_score": most_common_score,
        "data_support_counts": data_support_counts,
        "confidence_counts": confidence_counts,
        "style_inputs_available_count": style_count,
        "style_inputs_missing_count": int(len(rows) - style_count),
        "rating_only_or_fixture_only_count": rating_only_count,
        "missing_data_flag_count": missing_data_count,
        "warning_count": int(len(flags)),
        "flag_counts": dict(Counter(flags["flag_type"].tolist())) if not flags.empty else {},
        "baseline_to_beat": (
            "Future style adjustments must improve calibration or review quality beyond this rating/fixture baseline "
            "without increasing sanity flags, overclaiming style inputs, or adding action language."
        ),
        "plain_english_conclusion": (
            "Sample/demo rows are not real current matchups."
            if sample_count and real_count == 0 and manual_count == 0
            else "Current output is usable as a rating-based baseline. It is not style-aware yet."
        ),
    }


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    if not rows:
        return ["No rows."]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        values = [str(row.get(column, "")).replace("|", "\\|").replace("\n", " ") for column in columns]
        lines.append("| " + " | ".join(values) + " |")
    return lines


def build_checkpoint_summary_markdown(summary: dict[str, Any], rows: pd.DataFrame, flags: pd.DataFrame, source_path: str) -> str:
    review_rows = rows.head(12).to_dict("records") if not rows.empty else []
    flag_rows = flags.head(20).to_dict("records") if not flags.empty else []
    lines = [
        "# Projection Results Checkpoint",
        "",
        "## Executive Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Rows reviewed: `{summary['rows_reviewed']}`",
        f"- Real/manual/sample rows: `{summary['real_rows_reviewed']}` / `{summary['manual_rows_reviewed']}` / `{summary['sample_rows_reviewed']}`",
        f"- Source projection file: `{source_path}`",
        f"- Average projected total: `{summary['average_projected_total']}`",
        f"- Most common single highest-probability score cell: `{summary['most_common_likely_score']}`",
        f"- Warning flags: `{summary['warning_count']}`",
        f"- Conclusion: {summary['plain_english_conclusion']}",
        "",
        "## What Current Baseline Can Do",
        "",
        "- Produce score totals, W/D/L probabilities, most likely exact score cells, and confidence/context labels from current fixture plus rating support.",
        "- Keep the rating-only baseline visible as a benchmark for future style-aware adjustments.",
        "- Surface projection rows that need human review before any downstream reporting.",
        "",
        "## What It Cannot Do Yet",
        "",
        "- It does not activate true current event, tracking, lineup, xG, or 360 style inputs.",
        "- It does not treat fixture-only or rating-only support as a style-aware projection.",
        "- It does not produce betting picks, action recommendations, or certainty claims.",
        "",
        "## Projection Sanity",
        "",
        f"- Projected total range: `{summary['min_projected_total']}` to `{summary['max_projected_total']}`",
        f"- Missing data flags: `{summary['missing_data_flag_count']}`",
        f"- Flag counts: `{summary['flag_counts']}`",
        "",
        "## Data Support / Confidence",
        "",
        f"- Data support counts: `{summary['data_support_counts']}`",
        f"- Confidence counts: `{summary['confidence_counts']}`",
        f"- Rating-only or fixture-only rows: `{summary['rating_only_or_fixture_only_count']}`",
        "",
        "## Style Input Status",
        "",
        f"- Rows with style inputs available: `{summary['style_inputs_available_count']}`",
        f"- Rows without style inputs available: `{summary['style_inputs_missing_count']}`",
        "- Current style inputs remain inactive unless a row explicitly carries measurable style evidence.",
        "",
        "## Rows to Review",
        "",
    ]
    lines.extend(_markdown_table(review_rows, [
        "team_a",
        "team_b",
        "projected_total",
        "most_likely_score",
        "home_win_probability",
        "draw_probability",
        "away_win_probability",
        "confidence_label",
        "data_support_level",
        "rating_status",
        "source_tier",
        "is_sample_data",
        "style_inputs_available",
    ]))
    lines.extend(["", "## Warning Rows", ""])
    lines.extend(_markdown_table(flag_rows, ["source_row_index", "team_a", "team_b", "flag_type", "message"]))
    lines.extend([
        "",
        "## Baseline to Beat Next",
        "",
        summary["baseline_to_beat"],
        "",
        "## Recommended Next Step",
        "",
        "Use this checkpoint as the no-style baseline. The next style-adjustment phase should compare any style-aware adjustment against these rows and keep support labels honest when style inputs are missing.",
        "",
    ])
    return "\n".join(lines)


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _write_projection_consistency(
    *,
    current_projection_result: dict[str, Any],
    checkpoint_rows: pd.DataFrame,
) -> dict[str, Any]:
    run_dir = Path(current_projection_result["run_dir"]) / "fixture_deduplication"
    run_dir.mkdir(parents=True, exist_ok=True)
    direct = current_projection_result.get("projections", pd.DataFrame()).copy()
    direct_keys = [str(value) for value in direct.get("fixture_key", pd.Series(dtype=str)).tolist()]
    checkpoint_keys = [str(value) for value in checkpoint_rows.get("fixture_key", pd.Series(dtype=str)).tolist()]
    duplicate_direct = sorted({key for key in direct_keys if key and direct_keys.count(key) > 1})
    status = "pass" if direct_keys == checkpoint_keys and not duplicate_direct and len(direct) == len(checkpoint_rows) else "warning"
    rows = []
    for idx in range(max(len(direct_keys), len(checkpoint_keys))):
        rows.append({
            "row_number": idx + 1,
            "direct_fixture_key": direct_keys[idx] if idx < len(direct_keys) else "",
            "checkpoint_fixture_key": checkpoint_keys[idx] if idx < len(checkpoint_keys) else "",
            "matches": idx < len(direct_keys) and idx < len(checkpoint_keys) and direct_keys[idx] == checkpoint_keys[idx],
        })
    check_path = run_dir / "dedupe_consistency_check.csv"
    summary_path = run_dir / "projection_checkpoint_consistency.md"
    pd.DataFrame(rows).to_csv(check_path, index=False)
    summary_path.write_text(
        "\n".join([
            "# Projection Checkpoint Consistency",
            "",
            f"- Status: `{status}`",
            f"- Direct projection rows: `{len(direct)}`",
            f"- Checkpoint rows: `{len(checkpoint_rows)}`",
            f"- Fixture keys match in order: `{direct_keys == checkpoint_keys}`",
            f"- Duplicate direct fixture keys: `{duplicate_direct}`",
            "",
            "The checkpoint reads the direct projection output generated by the same current-international pipeline.",
        ]),
        encoding="utf-8",
    )
    return {
        "status": status,
        "direct_projection_rows": int(len(direct)),
        "checkpoint_rows": int(len(checkpoint_rows)),
        "fixture_keys_match": direct_keys == checkpoint_keys,
        "duplicate_direct_fixture_keys": duplicate_direct,
        "paths": {
            "dedupe_consistency_check": str(check_path),
            "projection_checkpoint_consistency": str(summary_path),
        },
    }


def _latest_projection_file() -> Path | None:
    roots = [
        Path("outputs/current_international"),
        Path("outputs/projections"),
        Path("outputs/runs"),
    ]
    candidates: list[Path] = []
    for root in roots:
        if root.exists():
            candidates.extend(root.rglob("*projections*.csv"))
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def run_projection_checkpoint(
    *,
    as_of_date: str | None = None,
    projection_file: str | Path | None = None,
    run_current_international: bool = False,
    manual_matchups: str | Path | None = None,
    max_matches: int = 10,
    allow_network: bool = False,
    cache_dir: str | Path = "data/source_cache/current_international",
    output_dir: str | Path = "outputs/projection_checkpoints",
    build_viewer: bool = False,
    allow_sample_data: bool = False,
    build_poisson_board: bool = False,
    max_goals: int = 6,
    slate_window: str = "default",
    days_ahead: int = 7,
    date_from: str | None = None,
    date_to: str | None = None,
    include_past: bool = False,
    dedupe_fixtures: bool = True,
    dedupe_review_threshold: float = 0.75,
    source_priority_mode: str = "balanced",
) -> dict[str, Any]:
    run_date = _run_date(as_of_date)
    source_path: Path | None = Path(projection_file) if projection_file else None
    current_projection_result: dict[str, Any] | None = None

    if run_current_international:
        from src.international_current.current_international_slate import project_current_international

        current_output_dir = Path(output_dir).parent / "current_international"
        current_projection_result = project_current_international(
            as_of_date=run_date,
            manual_matchups=manual_matchups,
            allow_network=allow_network,
            allow_sample_data=allow_sample_data,
            max_matches=max_matches,
            cache_dir=cache_dir,
            output_dir=current_output_dir,
            slate_window=slate_window,
            days_ahead=days_ahead,
            date_from=date_from,
            date_to=date_to,
            include_past=include_past,
            dedupe_fixtures=dedupe_fixtures,
            dedupe_review_threshold=dedupe_review_threshold,
            source_priority_mode=source_priority_mode,
        )
        source_path = Path(current_projection_result["projections_path"])
    elif source_path is None:
        source_path = _latest_projection_file()

    if source_path is None:
        raise ValueError("No projection file found. Provide --projection-file or use --run-current-international.")
    if not source_path.exists():
        raise FileNotFoundError(f"Projection file does not exist: {source_path}")

    source_frame = _read_projection_file(source_path)
    analysis = analyze_projection_rows(source_frame)
    rows = analysis["rows"]
    flags = analysis["flags"]
    summary = analysis["summary"]
    if current_projection_result:
        current_manifest = current_projection_result.get("manifest", {})
        skipped_placeholders = int(current_manifest.get("skipped_placeholder_rows") or 0)
        if skipped_placeholders:
            extra_flag = pd.DataFrame([{
                "source_row_index": -1,
                "team_a": "",
                "team_b": "",
                "flag_type": "unresolved_placeholder_fixtures_skipped",
                "severity": "warning",
                "message": "Unresolved placeholder fixtures were skipped and not projected.",
            }])
            flags = pd.concat([flags, extra_flag], ignore_index=True)
            summary = _summarize_checkpoint(rows, flags, "warning")
    consistency: dict[str, Any] = {}
    if current_projection_result:
        consistency = _write_projection_consistency(current_projection_result=current_projection_result, checkpoint_rows=rows)
        if consistency["status"] != "pass":
            extra_flag = pd.DataFrame([{
                "source_row_index": -1,
                "team_a": "",
                "team_b": "",
                "flag_type": "direct_checkpoint_fixture_mismatch",
                "severity": "warning",
                "message": "Direct current projection fixture keys differ from checkpoint rows.",
            }])
            flags = pd.concat([flags, extra_flag], ignore_index=True)
            summary = _summarize_checkpoint(rows, flags, "warning")

    checkpoint_dir = Path(output_dir) / run_date
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    rows_path = checkpoint_dir / "projection_checkpoint_rows.csv"
    flags_path = checkpoint_dir / "projection_checkpoint_flags.csv"
    summary_path = checkpoint_dir / "projection_checkpoint_summary.md"
    manifest_path = checkpoint_dir / "projection_checkpoint_manifest.json"
    poisson_result: dict[str, Any] | None = None
    has_valid_xg = (
        not rows.empty
        and "projected_home_xg" in rows
        and "projected_away_xg" in rows
        and rows[["projected_home_xg", "projected_away_xg"]].notna().all(axis=1).any()
    )
    if build_poisson_board or has_valid_xg:
        poisson_result = write_poisson_outputs(rows, checkpoint_dir / "poisson", max_goals=max_goals)

    rows.to_csv(rows_path, index=False)
    flags.to_csv(flags_path, index=False)
    summary_path.write_text(build_checkpoint_summary_markdown(summary, rows, flags, str(source_path)), encoding="utf-8")
    manifest = {
        "run_id": f"projection_checkpoint_{run_date}",
        "run_date": run_date,
        "generated_at": _now_iso(),
        "status": summary["status"],
        "checkpoint_type": "projection_results_checkpoint",
        "source_projection_file": str(source_path),
        "run_current_international": run_current_international,
        "allow_network": allow_network,
        "allow_sample_data": allow_sample_data,
        "manual_matchups": str(manual_matchups) if manual_matchups else "",
        "max_matches": max_matches,
        "slate_window": slate_window,
        "days_ahead": days_ahead,
        "date_from": date_from or "",
        "date_to": date_to or "",
        "include_past": include_past,
        "dedupe_fixtures": dedupe_fixtures,
        "dedupe_review_threshold": dedupe_review_threshold,
        "source_priority_mode": source_priority_mode,
        "build_poisson_board": bool(poisson_result),
        "max_goals": max_goals,
        "rows_reviewed": summary["rows_reviewed"],
        "real_rows_reviewed": summary["real_rows_reviewed"],
        "manual_rows_reviewed": summary["manual_rows_reviewed"],
        "sample_rows_reviewed": summary["sample_rows_reviewed"],
        "warning_count": summary["warning_count"],
        "style_inputs_available_count": summary["style_inputs_available_count"],
        "data_support_counts": summary["data_support_counts"],
        "confidence_counts": summary["confidence_counts"],
        "flag_counts": summary["flag_counts"],
        "baseline_to_beat": summary["baseline_to_beat"],
        "output_paths": {
            "summary": str(summary_path),
            "rows": str(rows_path),
            "flags": str(flags_path),
            "manifest": str(manifest_path),
            "poisson": poisson_result["paths"] if poisson_result else {},
        },
        "current_projection_output_paths": (
            current_projection_result.get("manifest", {}).get("output_paths", {})
            if current_projection_result
            else {}
        ),
        "current_projection_slate_selection": (
            current_projection_result.get("manifest", {}).get("slate_selection", {})
            if current_projection_result
            else {}
        ),
        "current_projection_deduplication": (
            {
                key: current_projection_result.get("manifest", {}).get(key)
                for key in [
                    "fixture_rows_before_dedupe",
                    "fixture_rows_after_dedupe",
                    "duplicate_rows_skipped",
                    "possible_duplicate_review_rows",
                    "selected_primary_source_counts",
                    "duplicates_by_source_pair",
                ]
            }
            if current_projection_result
            else {}
        ),
        "projection_checkpoint_consistency": consistency,
    }
    _write_json(manifest_path, manifest)

    viewer_result: dict[str, Any] | None = None
    if build_viewer:
        from src.viewer.static_viewer import build_static_viewer

        viewer_result = build_static_viewer("outputs", "outputs/viewer")

    return {
        "status": summary["status"],
        "summary": summary,
        "rows": rows,
        "flags": flags,
        "source_projection_file": source_path,
        "checkpoint_dir": checkpoint_dir,
        "summary_path": summary_path,
        "rows_path": rows_path,
        "flags_path": flags_path,
        "manifest_path": manifest_path,
        "manifest": manifest,
        "viewer": viewer_result,
        "poisson": poisson_result,
    }


def format_checkpoint_terminal(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "Projection Results Checkpoint",
        f"Status: {summary['status']}",
        f"Rows reviewed: {summary['real_rows_reviewed']} real rows, {summary['manual_rows_reviewed']} manual rows, {summary['sample_rows_reviewed']} sample/demo rows",
        f"Average projected total: {summary['average_projected_total']}",
        f"Most common single highest-probability score cell: {summary['most_common_likely_score']}",
        f"Data support counts: {summary['data_support_counts']}",
        f"Style inputs available rows: {summary['style_inputs_available_count']}",
        f"Warnings: {summary['warning_count']}",
        f"Output path: {result['checkpoint_dir']}",
    ]
    poisson = result.get("poisson")
    if poisson:
        match_summary = poisson["tables"]["match_summary"]
        if not match_summary.empty:
            top_home = match_summary.sort_values("home_win_probability", ascending=False).iloc[0]
            top_away = match_summary.sort_values("away_win_probability", ascending=False).iloc[0]
            top_over = match_summary.sort_values("over_2_5_probability", ascending=False).iloc[0]
            lines.extend([
                "",
                "Poisson Output",
                "Poisson board: written",
                f"Highest home win probability: {top_home['home_team']} vs {top_home['away_team']} ({float(top_home['home_win_probability']):.3f})",
                f"Highest away win probability: {top_away['home_team']} vs {top_away['away_team']} ({float(top_away['away_win_probability']):.3f})",
                f"Highest over 2.5 probability: {top_over['home_team']} vs {top_over['away_team']} ({float(top_over['over_2_5_probability']):.3f})",
                f"Most common single highest-probability score cell: {match_summary['most_likely_score'].mode().iloc[0]}",
                f"Poisson output path: {result['checkpoint_dir'] / 'poisson'}",
            ])
        else:
            lines.extend(["", "Poisson Output", "Poisson board: skipped, no valid projected xG rows"])
    if result.get("viewer"):
        lines.append(f"Viewer: {result['viewer']['viewer_output_path']}")
    return "\n".join(lines)
