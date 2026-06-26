from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


SLATE_SELECTION_COLUMNS = [
    "fixture_date",
    "kickoff_time",
    "kickoff_datetime_utc",
    "fixture_date_status",
    "fixture_temporal_status",
    "is_current_slate",
    "slate_window_status",
    "slate_skip_reason",
    "slate_window",
    "selected_by_slate_filter",
]


def normalize_slate_window(value: str | None) -> str:
    text = str(value or "default").strip().lower().replace("-", "_")
    if text in {"", "auto"}:
        return "default"
    if text == "date":
        return "date_range"
    if text not in {"default", "today", "next", "upcoming", "date_range", "all_resolved"}:
        raise ValueError(f"Unsupported slate window: {value}")
    return text


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _iso(value: date | None) -> str:
    return value.isoformat() if value else ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _temporal_status(fixture_date: date | None, as_of: date) -> str:
    if fixture_date is None:
        return "unknown_date"
    if fixture_date < as_of:
        return "past"
    if fixture_date == as_of:
        return "today"
    return "upcoming"


def _sort_slate(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    sort_cols = [col for col in ["fixture_date", "kickoff_time", "home_team", "away_team"] if col in frame.columns]
    return frame.sort_values(sort_cols, na_position="last").reset_index(drop=True)


def _selected_reason(window: str, effective_window: str, fixture_date: date | None, as_of: date) -> str:
    if effective_window == "all_resolved":
        return "selected_all_resolved"
    if effective_window == "date_range":
        return "selected_date_range"
    if effective_window == "upcoming":
        return "selected_upcoming"
    if fixture_date == as_of:
        return "selected_today"
    if window in {"default", "next"}:
        return "selected_next_upcoming"
    return "selected_by_slate_filter"


def apply_slate_selection(
    frame: pd.DataFrame,
    *,
    as_of_date: str,
    slate_window: str | None = "default",
    days_ahead: int = 7,
    date_from: str | None = None,
    date_to: str | None = None,
    include_past: bool = False,
) -> dict[str, Any]:
    as_of = _parse_date(as_of_date)
    if as_of is None:
        raise ValueError(f"Invalid as_of_date: {as_of_date}")
    window = normalize_slate_window(slate_window)
    days = max(0, int(days_ahead or 0))
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if window == "date_range":
        start = start or as_of
        end = end or start
    elif window == "upcoming":
        start = as_of
        end = as_of + timedelta(days=days)
    elif window == "today":
        start = as_of
        end = as_of

    annotated = frame.copy()
    for column in SLATE_SELECTION_COLUMNS:
        if column not in annotated.columns:
            annotated[column] = ""
    if annotated.empty:
        summary = _summary(annotated, as_of, window, window, days, start, end, include_past)
        return {"annotated_slate": annotated, "selected_slate": annotated.copy(), "summary": summary}

    parsed_dates = annotated.get("match_date", pd.Series(dtype=object)).apply(_parse_date)
    annotated["fixture_date"] = parsed_dates.apply(_iso)
    annotated["kickoff_time"] = annotated.get("kickoff_time", pd.Series([""] * len(annotated))).fillna("").astype(str)
    annotated["kickoff_datetime_utc"] = ""
    annotated["fixture_date_status"] = parsed_dates.apply(lambda item: "valid_date" if item else "unknown_date")
    annotated["fixture_temporal_status"] = parsed_dates.apply(lambda item: _temporal_status(item, as_of))
    annotated["is_current_slate"] = False
    annotated["selected_by_slate_filter"] = False
    annotated["slate_window"] = window
    annotated["slate_window_status"] = "skipped_by_date"
    annotated["slate_skip_reason"] = ""

    eligible_mask = annotated.get("projection_eligible", pd.Series([True] * len(annotated))).apply(_truthy)
    unresolved_mask = annotated.get("fixture_resolution_status", pd.Series([""] * len(annotated))).astype(str).eq("unresolved_placeholder")
    sample_skip_mask = annotated.get("projection_skip_reason", pd.Series([""] * len(annotated))).astype(str).eq("sample_requires_allow_sample_data")

    annotated.loc[unresolved_mask, "slate_window_status"] = "skipped_unresolved"
    annotated.loc[unresolved_mask, "slate_skip_reason"] = "unresolved_placeholder"
    annotated.loc[sample_skip_mask, "slate_window_status"] = "skipped_unresolved"
    annotated.loc[sample_skip_mask, "slate_skip_reason"] = "sample_requires_allow_sample_data"
    non_projection_mask = ~eligible_mask & ~unresolved_mask & ~sample_skip_mask
    annotated.loc[non_projection_mask, "slate_window_status"] = "skipped_unresolved"
    annotated.loc[non_projection_mask, "slate_skip_reason"] = annotated.loc[non_projection_mask, "projection_skip_reason"].fillna("").astype(str)

    eligible_dates = parsed_dates[eligible_mask]
    effective_window = window
    selected_mask = pd.Series([False] * len(annotated), index=annotated.index)

    if window == "all_resolved":
        selected_mask = eligible_mask
    elif window == "next":
        future_dates = sorted({item for item in eligible_dates if item is not None and item >= as_of})
        next_date = future_dates[0] if future_dates else None
        selected_mask = eligible_mask & parsed_dates.eq(next_date) if next_date else selected_mask
    elif window == "today":
        selected_mask = eligible_mask & parsed_dates.eq(as_of)
    elif window == "upcoming":
        selected_mask = eligible_mask & parsed_dates.apply(lambda item: item is not None and start <= item <= end)
    elif window == "date_range":
        selected_mask = eligible_mask & parsed_dates.apply(lambda item: item is not None and start <= item <= end)
    else:
        today_mask = eligible_mask & parsed_dates.eq(as_of)
        if today_mask.any():
            selected_mask = today_mask
            effective_window = "today"
        else:
            future_dates = sorted({item for item in eligible_dates if item is not None and item > as_of})
            next_date = future_dates[0] if future_dates else None
            selected_mask = eligible_mask & parsed_dates.eq(next_date) if next_date else selected_mask
            effective_window = "next"

    if not include_past and window not in {"all_resolved"}:
        past_selected = selected_mask & parsed_dates.apply(lambda item: item is not None and item < as_of)
        selected_mask = selected_mask & ~past_selected

    annotated.loc[selected_mask, "is_current_slate"] = True
    annotated.loc[selected_mask, "selected_by_slate_filter"] = True
    annotated.loc[selected_mask, "slate_skip_reason"] = ""
    annotated.loc[selected_mask, "slate_window_status"] = [
        _selected_reason(window, effective_window, parsed_dates.loc[index], as_of)
        for index in annotated.index[selected_mask]
    ]

    skipped_date_mask = eligible_mask & ~selected_mask
    for index in annotated.index[skipped_date_mask]:
        fixture_date = parsed_dates.loc[index]
        if fixture_date is None:
            reason = "unknown_fixture_date"
        elif not include_past and fixture_date < as_of and window != "all_resolved":
            reason = "fixture_before_as_of_date"
        elif window == "today" or effective_window == "today":
            reason = "fixture_not_on_as_of_date"
        elif window in {"upcoming", "date_range"} and end and fixture_date > end:
            reason = "fixture_after_window"
        elif window in {"upcoming", "date_range"} and start and fixture_date < start:
            reason = "fixture_before_window"
        elif window in {"default", "next"}:
            reason = "fixture_not_next_upcoming_date"
        else:
            reason = "not_selected_by_slate_filter"
        annotated.at[index, "slate_skip_reason"] = reason

    annotated["slate_window"] = effective_window if window == "default" else window
    annotated = _sort_slate(annotated)
    selected = _sort_slate(annotated[annotated["selected_by_slate_filter"].apply(_truthy)].copy())
    summary = _summary(annotated, as_of, window, effective_window, days, start, end, include_past)
    return {"annotated_slate": annotated, "selected_slate": selected, "summary": summary}


def _summary(
    frame: pd.DataFrame,
    as_of: date,
    requested_window: str,
    effective_window: str,
    days_ahead: int,
    date_from: date | None,
    date_to: date | None,
    include_past: bool,
) -> dict[str, Any]:
    if frame.empty:
        return {
            "as_of_date": as_of.isoformat(),
            "slate_window": requested_window,
            "effective_slate_window": effective_window,
            "days_ahead": days_ahead,
            "date_from": _iso(date_from),
            "date_to": _iso(date_to),
            "include_past": include_past,
            "total_harvested_fixtures": 0,
            "resolved_fixtures": 0,
            "unresolved_fixtures": 0,
            "fixtures_before_as_of_date": 0,
            "fixtures_on_as_of_date": 0,
            "upcoming_fixtures": 0,
            "selected_fixtures": 0,
            "skipped_by_date_fixtures": 0,
            "skipped_past_fixtures": 0,
            "skipped_future_outside_window_fixtures": 0,
            "skipped_unresolved_fixtures": 0,
            "selected_date_range": "",
            "earliest_selected_fixture_date": "",
            "latest_selected_fixture_date": "",
            "default_used_next_upcoming": False,
        }
    selected = frame[frame["selected_by_slate_filter"].apply(_truthy)]
    fixture_dates = frame["fixture_date"].apply(_parse_date)
    selected_dates = selected["fixture_date"].apply(_parse_date) if not selected.empty else pd.Series(dtype=object)
    skip_reasons = frame.get("slate_skip_reason", pd.Series(dtype=str)).astype(str)
    earliest = min([item for item in selected_dates if item is not None], default=None)
    latest = max([item for item in selected_dates if item is not None], default=None)
    return {
        "as_of_date": as_of.isoformat(),
        "slate_window": requested_window,
        "effective_slate_window": effective_window,
        "days_ahead": days_ahead,
        "date_from": _iso(date_from),
        "date_to": _iso(date_to),
        "include_past": include_past,
        "total_harvested_fixtures": int(len(frame)),
        "resolved_fixtures": int(frame.get("is_resolved_fixture", pd.Series(dtype=bool)).apply(_truthy).sum()),
        "unresolved_fixtures": int((frame.get("fixture_resolution_status", pd.Series(dtype=str)).astype(str) == "unresolved_placeholder").sum()),
        "fixtures_before_as_of_date": int(fixture_dates.apply(lambda item: item is not None and item < as_of).sum()),
        "fixtures_on_as_of_date": int(fixture_dates.apply(lambda item: item == as_of).sum()),
        "upcoming_fixtures": int(fixture_dates.apply(lambda item: item is not None and item > as_of).sum()),
        "selected_fixtures": int(len(selected)),
        "skipped_by_date_fixtures": int((frame.get("projection_eligible", pd.Series(dtype=bool)).apply(_truthy) & ~frame["selected_by_slate_filter"].apply(_truthy)).sum()),
        "skipped_past_fixtures": int(skip_reasons.eq("fixture_before_as_of_date").sum()),
        "skipped_future_outside_window_fixtures": int(skip_reasons.eq("fixture_after_window").sum()),
        "skipped_unresolved_fixtures": int((frame["slate_window_status"].astype(str) == "skipped_unresolved").sum()),
        "selected_date_range": f"{_iso(earliest)} to {_iso(latest)}" if earliest or latest else "",
        "earliest_selected_fixture_date": _iso(earliest),
        "latest_selected_fixture_date": _iso(latest),
        "default_used_next_upcoming": bool(requested_window == "default" and effective_window == "next" and len(selected) > 0),
    }


def write_slate_selection_outputs(
    *,
    run_dir: str | Path,
    annotated_slate: pd.DataFrame,
    summary: dict[str, Any],
) -> dict[str, str]:
    output = Path(run_dir) / "slate_selection"
    output.mkdir(parents=True, exist_ok=True)
    selected = annotated_slate[annotated_slate["selected_by_slate_filter"].apply(_truthy)] if not annotated_slate.empty else annotated_slate
    eligible = annotated_slate[annotated_slate.get("projection_eligible", pd.Series(dtype=bool)).apply(_truthy)] if not annotated_slate.empty else annotated_slate
    skipped_by_date = eligible[~eligible["selected_by_slate_filter"].apply(_truthy)] if not eligible.empty else eligible
    skipped_unresolved = annotated_slate[annotated_slate["slate_window_status"].astype(str) == "skipped_unresolved"] if not annotated_slate.empty else annotated_slate
    all_resolved = annotated_slate[annotated_slate.get("is_resolved_fixture", pd.Series(dtype=bool)).apply(_truthy)] if not annotated_slate.empty else annotated_slate

    paths = {
        "slate_selection_summary": output / "slate_selection_summary.md",
        "selected_fixtures": output / "selected_fixtures.csv",
        "skipped_by_date_fixtures": output / "skipped_by_date_fixtures.csv",
        "skipped_unresolved_fixtures": output / "skipped_unresolved_fixtures.csv",
        "all_resolved_fixtures": output / "all_resolved_fixtures.csv",
    }
    selected.to_csv(paths["selected_fixtures"], index=False)
    skipped_by_date.to_csv(paths["skipped_by_date_fixtures"], index=False)
    skipped_unresolved.to_csv(paths["skipped_unresolved_fixtures"], index=False)
    all_resolved.to_csv(paths["all_resolved_fixtures"], index=False)

    lines = [
        "# Current International Slate Selection",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Selection Parameters",
        "",
        f"- As-of date: `{summary['as_of_date']}`",
        f"- Requested slate window: `{summary['slate_window']}`",
        f"- Effective slate window: `{summary['effective_slate_window']}`",
        f"- Days ahead: `{summary['days_ahead']}`",
        f"- Date from: `{summary['date_from'] or 'not set'}`",
        f"- Date to: `{summary['date_to'] or 'not set'}`",
        f"- Include past fixtures: `{summary['include_past']}`",
        "",
        "## Counts",
        "",
        f"- Total harvested fixtures: `{summary['total_harvested_fixtures']}`",
        f"- Resolved fixtures: `{summary['resolved_fixtures']}`",
        f"- Unresolved fixtures: `{summary['unresolved_fixtures']}`",
        f"- Fixtures before as-of date: `{summary['fixtures_before_as_of_date']}`",
        f"- Fixtures on as-of date: `{summary['fixtures_on_as_of_date']}`",
        f"- Upcoming fixtures: `{summary['upcoming_fixtures']}`",
        f"- Selected fixtures: `{summary['selected_fixtures']}`",
        f"- Skipped by date/window: `{summary['skipped_by_date_fixtures']}`",
        f"- Skipped past fixtures: `{summary['skipped_past_fixtures']}`",
        f"- Skipped future/outside-window fixtures: `{summary['skipped_future_outside_window_fixtures']}`",
        f"- Skipped unresolved fixtures: `{summary['skipped_unresolved_fixtures']}`",
        "",
        "## Selected Date Range",
        "",
        f"- Selected date range: `{summary['selected_date_range'] or 'none'}`",
        f"- Earliest selected fixture date: `{summary['earliest_selected_fixture_date'] or 'none'}`",
        f"- Latest selected fixture date: `{summary['latest_selected_fixture_date'] or 'none'}`",
        "",
        "## Guardrails",
        "",
        "- No fixtures are invented.",
        "- Unresolved placeholders are not projected.",
        "- Kickoff UTC is only filled when source data provides it.",
        "- Current StatsBomb is not used.",
        "- Proxy score adjustments remain disabled.",
        "- Output is projection review context, not wagering guidance.",
        "",
    ]
    paths["slate_selection_summary"].write_text("\n".join(lines), encoding="utf-8")
    return {key: str(value) for key, value in paths.items()}
