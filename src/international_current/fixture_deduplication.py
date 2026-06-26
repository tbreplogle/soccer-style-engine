from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.international_current.kickoff_normalization import kickoff_delta_minutes, normalize_kickoff_time


DEDUPLICATION_COLUMNS = [
    "fixture_key",
    "dedupe_match_key",
    "deduplication_status",
    "duplicate_group_id",
    "primary_source",
    "duplicate_sources",
    "dedupe_reason",
    "dedupe_confidence",
    "dedupe_time_comparison",
    "dedupe_time_delta_minutes",
    "dedupe_time_normalization_status",
    "source_priority_score",
    "source_priority_reason",
    "kickoff_time_raw",
    "kickoff_time_normalized",
    "kickoff_datetime_normalized",
    "kickoff_timezone_status",
    "kickoff_parse_warning",
]


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _fixture_date(row: pd.Series) -> str:
    return str(row.get("fixture_date") or row.get("match_date") or "")[:10]


def _source(row: pd.Series) -> str:
    return str(row.get("source_fixture_name") or row.get("fixture_source_name") or row.get("source_name") or "")


def fixture_key(row: pd.Series) -> str:
    parts = [
        _fixture_date(row),
        _norm(row.get("competition")),
        _norm(row.get("home_team")),
        _norm(row.get("away_team")),
    ]
    return "|".join(parts)


def dedupe_match_key(row: pd.Series) -> str:
    resolved = "resolved" if _truthy(row.get("is_resolved_fixture", True)) else str(row.get("fixture_resolution_status") or "unresolved")
    parts = [
        _fixture_date(row),
        _norm(row.get("competition")),
        _norm(row.get("home_team")),
        _norm(row.get("away_team")),
        _norm(resolved),
    ]
    return "|".join(parts)


def swapped_fixture_key(row: pd.Series) -> str:
    parts = [
        _fixture_date(row),
        _norm(row.get("competition")),
        _norm(row.get("away_team")),
        _norm(row.get("home_team")),
    ]
    return "|".join(parts)


def swapped_dedupe_match_key(row: pd.Series) -> str:
    resolved = "resolved" if _truthy(row.get("is_resolved_fixture", True)) else str(row.get("fixture_resolution_status") or "unresolved")
    parts = [
        _fixture_date(row),
        _norm(row.get("competition")),
        _norm(row.get("away_team")),
        _norm(row.get("home_team")),
        _norm(resolved),
    ]
    return "|".join(parts)


def source_priority_score(row: pd.Series, *, mode: str = "balanced") -> tuple[int, str]:
    score = 0
    reasons: list[str] = []
    source = _source(row)
    source_lower = source.lower()
    if _fixture_date(row):
        score += 25
        reasons.append("fixture_date_present")
    kickoff_status = str(row.get("kickoff_timezone_status") or "").strip()
    if str(row.get("kickoff_time") or row.get("kickoff_time_normalized") or "").strip():
        score += 20
        reasons.append("kickoff_time_present")
    if kickoff_status == "known_offset":
        score += 8
        reasons.append("kickoff_offset_known")
    if _truthy(row.get("is_resolved_fixture", True)):
        score += 20
        reasons.append("resolved_teams")
    if str(row.get("competition") or "").strip():
        score += 8
        reasons.append("competition_present")
    if str(row.get("round_name") or "").strip():
        score += 4
        reasons.append("round_present")
    if str(row.get("group_name") or "").strip():
        score += 4
        reasons.append("group_present")
    tier = str(row.get("source_tier") or "").lower()
    if tier == "real":
        score += 8
        reasons.append("real_source")
    elif tier == "manual":
        score += 4
        reasons.append("manual_source")
    elif tier == "sample":
        reasons.append("sample_source")
    if "espn" in source_lower and str(row.get("kickoff_time") or "").strip():
        score += 12
        reasons.append("espn_with_time")
    elif "openfootball" in source_lower:
        score += 10
        reasons.append("openfootball_structure")
    elif "cache" in source_lower or str(row.get("reliability_status") or "").lower() in {"local_cache", "cached"}:
        score += 6
        reasons.append("cached_real_source")
    if str(row.get("source_fixture_status") or "").strip():
        score += 3
        reasons.append("source_status_present")
    if mode == "prefer_openfootball" and "openfootball" in source_lower:
        score += 12
        reasons.append("mode_prefer_openfootball")
    elif mode == "prefer_espn" and "espn" in source_lower:
        score += 12
        reasons.append("mode_prefer_espn")
    return score, " | ".join(reasons)


def deduplicate_fixtures(
    frame: pd.DataFrame,
    *,
    enabled: bool = True,
    review_threshold: float = 0.75,
    source_priority_mode: str = "balanced",
) -> dict[str, Any]:
    annotated = frame.copy()
    for column in DEDUPLICATION_COLUMNS:
        if column not in annotated.columns:
            annotated[column] = ""
    if annotated.empty:
        return {"deduplicated": annotated.copy(), "annotated": annotated, "duplicates": annotated.copy(), "review": annotated.copy(), "summary": _summary(annotated)}

    kickoff_rows = annotated.apply(lambda row: normalize_kickoff_time(row.get("kickoff_time", ""), row), axis=1)
    for column in ["kickoff_time_raw", "kickoff_time_normalized", "kickoff_datetime_normalized", "kickoff_timezone_status", "kickoff_parse_warning"]:
        annotated[column] = [item[column] for item in kickoff_rows]

    scores = annotated.apply(lambda row: source_priority_score(row, mode=source_priority_mode), axis=1)
    annotated["source_priority_score"] = [score for score, _ in scores]
    annotated["source_priority_reason"] = [reason for _, reason in scores]
    annotated["fixture_key"] = annotated.apply(fixture_key, axis=1)
    annotated["dedupe_match_key"] = annotated.apply(dedupe_match_key, axis=1)
    annotated["deduplication_status"] = "unique"
    annotated["duplicate_group_id"] = ""
    annotated["primary_source"] = annotated.apply(_source, axis=1)
    annotated["duplicate_sources"] = ""
    annotated["dedupe_reason"] = "dedupe_disabled" if not enabled else ""
    annotated["dedupe_confidence"] = 0.0
    annotated["dedupe_time_comparison"] = ""
    annotated["dedupe_time_delta_minutes"] = pd.NA
    annotated["dedupe_time_normalization_status"] = annotated["kickoff_timezone_status"]

    if not enabled:
        summary = _summary(annotated)
        return {"deduplicated": annotated.copy(), "annotated": annotated, "duplicates": annotated.iloc[0:0].copy(), "review": annotated.iloc[0:0].copy(), "summary": summary}

    keep_indices: set[int] = set(annotated.index)
    group_number = 0
    for key, group in annotated.groupby("dedupe_match_key", sort=False):
        if not key.strip() or len(group) <= 1:
            continue
        group_number += 1
        group_id = f"dup-{group_number:04d}"
        ordered = group.sort_values(["source_priority_score", "kickoff_time_normalized"], ascending=[False, False])
        primary_index = int(ordered.index[0])
        duplicate_indices = [int(index) for index in ordered.index[1:]]
        sources = sorted(set(_source(row) for _, row in group.iterrows() if _source(row)))
        primary_dt = annotated.at[primary_index, "kickoff_datetime_normalized"]
        annotated.loc[group.index, "duplicate_group_id"] = group_id
        annotated.at[primary_index, "deduplication_status"] = "kept_primary"
        annotated.at[primary_index, "primary_source"] = _source(annotated.loc[primary_index])
        annotated.at[primary_index, "duplicate_sources"] = " | ".join(source for source in sources if source != annotated.at[primary_index, "primary_source"])
        annotated.at[primary_index, "dedupe_reason"] = "same_date_teams_competition_resolved_status"
        annotated.at[primary_index, "dedupe_confidence"] = 0.95
        annotated.at[primary_index, "dedupe_time_comparison"] = "primary"
        for index in duplicate_indices:
            delta = kickoff_delta_minutes(primary_dt, annotated.at[index, "kickoff_datetime_normalized"])
            keep_indices.discard(index)
            annotated.at[index, "deduplication_status"] = "duplicate_skipped"
            annotated.at[index, "primary_source"] = annotated.at[primary_index, "primary_source"]
            annotated.at[index, "duplicate_sources"] = " | ".join(sources)
            annotated.at[index, "dedupe_reason"] = "lower_priority_duplicate_same_date_teams_competition"
            annotated.at[index, "dedupe_confidence"] = 0.95
            annotated.at[index, "dedupe_time_delta_minutes"] = delta if delta is not None else pd.NA
            annotated.at[index, "dedupe_time_comparison"] = (
                "within_tolerance"
                if delta is not None and delta <= 180
                else "timezone_missing_or_uncomparable"
                if delta is None
                else "same_fixture_key_time_differs"
            )

    review_indices: set[int] = set()
    exact_keys = set(annotated["dedupe_match_key"].astype(str))
    for index, row in annotated.iterrows():
        if index not in keep_indices:
            continue
        swapped = swapped_dedupe_match_key(row)
        if swapped not in exact_keys or swapped == row["dedupe_match_key"]:
            continue
        candidates = annotated[
            (annotated["dedupe_match_key"].astype(str) == swapped)
            & (annotated.index != index)
            & (annotated.index.isin(keep_indices))
        ]
        for candidate_index, candidate in candidates.iterrows():
            if _source(row) == _source(candidate):
                continue
            if not (_truthy(row.get("neutral_site")) and _truthy(candidate.get("neutral_site"))):
                continue
            review_indices.update({int(index), int(candidate_index)})

    for index in review_indices:
        if index not in keep_indices:
            continue
        group_number += 1
        annotated.at[index, "deduplication_status"] = "possible_duplicate_review"
        annotated.at[index, "duplicate_group_id"] = annotated.at[index, "duplicate_group_id"] or f"review-{group_number:04d}"
        annotated.at[index, "dedupe_reason"] = "possible_swapped_neutral_duplicate_different_sources"
        annotated.at[index, "dedupe_confidence"] = max(float(annotated.at[index, "dedupe_confidence"] or 0), min(0.74, review_threshold))

    deduplicated = annotated.loc[sorted(keep_indices)].copy().reset_index(drop=True)
    duplicates = annotated[annotated["deduplication_status"].eq("duplicate_skipped")].copy().reset_index(drop=True)
    review = annotated[annotated["deduplication_status"].eq("possible_duplicate_review")].copy().reset_index(drop=True)
    summary = _summary(annotated)
    return {"deduplicated": deduplicated, "annotated": annotated, "duplicates": duplicates, "review": review, "summary": summary}


def _summary(annotated: pd.DataFrame) -> dict[str, Any]:
    if annotated.empty:
        return {
            "fixture_rows_before_dedupe": 0,
            "fixture_rows_after_dedupe": 0,
            "duplicate_rows_skipped": 0,
            "possible_duplicate_review_rows": 0,
            "selected_primary_source_counts": {},
            "duplicates_by_source_pair": {},
        }
    kept = annotated[~annotated["deduplication_status"].eq("duplicate_skipped")]
    duplicates = annotated[annotated["deduplication_status"].eq("duplicate_skipped")]
    source_pairs = Counter()
    for _, row in duplicates.iterrows():
        pair = f"{row.get('primary_source', '')} <- {_source(row)}"
        source_pairs[pair] += 1
    return {
        "fixture_rows_before_dedupe": int(len(annotated)),
        "fixture_rows_after_dedupe": int(len(kept)),
        "duplicate_rows_skipped": int(len(duplicates)),
        "possible_duplicate_review_rows": int((annotated["deduplication_status"] == "possible_duplicate_review").sum()),
        "selected_primary_source_counts": dict(Counter(kept["primary_source"].astype(str))),
        "duplicates_by_source_pair": dict(source_pairs),
    }


def write_fixture_deduplication_outputs(
    *,
    run_dir: str | Path,
    dedupe_result: dict[str, Any],
) -> dict[str, str]:
    output = Path(run_dir) / "fixture_deduplication"
    output.mkdir(parents=True, exist_ok=True)
    deduplicated = dedupe_result["deduplicated"]
    duplicates = dedupe_result["duplicates"]
    review = dedupe_result["review"]
    annotated = dedupe_result["annotated"]
    summary = dedupe_result["summary"]
    source_priority = annotated[[
        col for col in [
            "match_date", "kickoff_time", "kickoff_time_raw", "kickoff_time_normalized",
            "kickoff_datetime_normalized", "kickoff_timezone_status", "home_team", "away_team",
            "source_fixture_name", "fixture_key", "dedupe_match_key", "deduplication_status",
            "source_priority_score", "source_priority_reason", "dedupe_time_comparison",
        ]
        if col in annotated.columns
    ]].copy()
    consistency = annotated[[
        col for col in [
            "match_date", "home_team", "away_team", "source_fixture_name", "fixture_key",
            "dedupe_match_key", "deduplication_status", "duplicate_group_id", "primary_source",
            "kickoff_time_raw", "kickoff_time_normalized", "dedupe_time_comparison",
            "dedupe_time_delta_minutes", "dedupe_reason",
        ]
        if col in annotated.columns
    ]].copy()
    paths = {
        "fixture_deduplication_summary": output / "fixture_deduplication_summary.md",
        "deduplicated_fixtures": output / "deduplicated_fixtures.csv",
        "duplicate_fixtures": output / "duplicate_fixtures.csv",
        "possible_duplicate_review": output / "possible_duplicate_review.csv",
        "source_priority_summary": output / "source_priority_summary.csv",
        "dedupe_consistency_check": output / "dedupe_consistency_check.csv",
        "projection_checkpoint_consistency": output / "projection_checkpoint_consistency.md",
    }
    deduplicated.to_csv(paths["deduplicated_fixtures"], index=False)
    duplicates.to_csv(paths["duplicate_fixtures"], index=False)
    review.to_csv(paths["possible_duplicate_review"], index=False)
    source_priority.to_csv(paths["source_priority_summary"], index=False)
    consistency.to_csv(paths["dedupe_consistency_check"], index=False)

    examples = duplicates.head(8).to_dict("records")
    lines = [
        "# Fixture Deduplication",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Counts",
        "",
        f"- Total input fixture rows: `{summary['fixture_rows_before_dedupe']}`",
        f"- Unique fixture rows kept: `{summary['fixture_rows_after_dedupe']}`",
        f"- Duplicate rows skipped: `{summary['duplicate_rows_skipped']}`",
        f"- Possible duplicates needing review: `{summary['possible_duplicate_review_rows']}`",
        f"- Selected primary source counts: `{summary['selected_primary_source_counts']}`",
        f"- Duplicates by source pair: `{summary['duplicates_by_source_pair']}`",
        "",
        "## Guardrails",
        "",
        "- Duplicate source rows are skipped only when the fixture key matches directly.",
        "- Kickoff strings are normalized for audit and priority, but exact date/team/competition matches dedupe even when kickoff formats differ.",
        "- Swapped neutral-site candidates are flagged for review, not silently merged.",
        "- No fixtures, kickoff times, or outcomes are invented.",
        "- Current StatsBomb is not used.",
        "- Output is projection review context, not wagering guidance.",
        "",
        "## Duplicate Examples",
        "",
    ]
    if examples:
        for item in examples:
            lines.append(
                f"- {item.get('match_date', '')} {item.get('home_team', '')} vs {item.get('away_team', '')}: "
                f"{item.get('source_fixture_name', '')} skipped; primary `{item.get('primary_source', '')}`."
            )
    else:
        lines.append("- none")
    paths["fixture_deduplication_summary"].write_text("\n".join(lines), encoding="utf-8")
    paths["projection_checkpoint_consistency"].write_text(
        "\n".join([
            "# Projection Checkpoint Consistency",
            "",
            "Checkpoint consistency has not been run for this direct slate build yet.",
            "Run `projection-results-checkpoint --run-current-international` to compare direct projection rows with checkpoint rows.",
        ]),
        encoding="utf-8",
    )
    return {key: str(value) for key, value in paths.items()}
