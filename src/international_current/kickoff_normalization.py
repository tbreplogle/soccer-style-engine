from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


OFFSET_RE = re.compile(r"\b(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?:UTC|GMT)\s*(?P<offset>[+-]\d{1,2})(?::?(?P<offset_minute>\d{2}))?\b", re.IGNORECASE)
TIME_RE = re.compile(r"\b(?P<hour>\d{1,2}):(?P<minute>\d{2})\b")


def _date_text(row_or_date: Any) -> str:
    if isinstance(row_or_date, dict) or hasattr(row_or_date, "get"):
        value = row_or_date.get("fixture_date") or row_or_date.get("match_date") or row_or_date.get("date") or ""
    else:
        value = row_or_date
    return str(value or "")[:10]


def _as_iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat(timespec="minutes")
    return value.astimezone(timezone.utc).isoformat(timespec="minutes")


def normalize_kickoff_time(kickoff_time: Any = "", fixture_date: Any = "") -> dict[str, Any]:
    raw = str(kickoff_time or "").strip()
    date_text = _date_text(fixture_date)
    if not raw:
        return {
            "kickoff_time_raw": raw,
            "kickoff_time_normalized": "",
            "kickoff_datetime_normalized": date_text,
            "kickoff_timezone_status": "date_only" if date_text else "missing",
            "kickoff_parse_warning": "Kickoff time missing; date-only fixture retained for audit.",
        }

    iso_candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        status = "known_offset" if parsed.tzinfo is not None else "time_no_timezone"
        return {
            "kickoff_time_raw": raw,
            "kickoff_time_normalized": parsed.time().isoformat(timespec="minutes"),
            "kickoff_datetime_normalized": _as_iso_utc(parsed),
            "kickoff_timezone_status": status,
            "kickoff_parse_warning": "" if parsed.tzinfo is not None else "Kickoff parsed without timezone; timezone not inferred.",
        }
    except ValueError:
        pass

    offset_match = OFFSET_RE.search(raw)
    if offset_match:
        hour = int(offset_match.group("hour"))
        minute = int(offset_match.group("minute"))
        offset_hour = int(offset_match.group("offset"))
        offset_minute = int(offset_match.group("offset_minute") or 0)
        offset_sign = 1 if offset_hour >= 0 else -1
        offset = timezone(timedelta(hours=offset_hour, minutes=offset_sign * offset_minute))
        try:
            parsed = datetime.fromisoformat(f"{date_text or '1900-01-01'}T{hour:02d}:{minute:02d}:00").replace(tzinfo=offset)
        except ValueError:
            return _parse_error(raw, date_text)
        return {
            "kickoff_time_raw": raw,
            "kickoff_time_normalized": f"{hour:02d}:{minute:02d} UTC{offset_hour:+03d}:{offset_minute:02d}",
            "kickoff_datetime_normalized": _as_iso_utc(parsed),
            "kickoff_timezone_status": "known_offset",
            "kickoff_parse_warning": "",
        }

    time_match = TIME_RE.search(raw)
    if time_match:
        hour = int(time_match.group("hour"))
        minute = int(time_match.group("minute"))
        if hour > 23 or minute > 59:
            return _parse_error(raw, date_text)
        normalized = f"{hour:02d}:{minute:02d}"
        return {
            "kickoff_time_raw": raw,
            "kickoff_time_normalized": normalized,
            "kickoff_datetime_normalized": f"{date_text}T{normalized}" if date_text else normalized,
            "kickoff_timezone_status": "time_no_timezone",
            "kickoff_parse_warning": "Kickoff time has no timezone; timezone not inferred.",
        }

    return _parse_error(raw, date_text)


def _parse_error(raw: str, date_text: str) -> dict[str, Any]:
    return {
        "kickoff_time_raw": raw,
        "kickoff_time_normalized": "",
        "kickoff_datetime_normalized": date_text,
        "kickoff_timezone_status": "parse_error",
        "kickoff_parse_warning": f"Could not parse kickoff time: {raw}",
    }


def kickoff_delta_minutes(left: Any, right: Any) -> float | None:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    if not left_text or not right_text:
        return None
    try:
        left_dt = datetime.fromisoformat(left_text.replace("Z", "+00:00"))
        right_dt = datetime.fromisoformat(right_text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if (left_dt.tzinfo is None) != (right_dt.tzinfo is None):
        return None
    if left_dt.tzinfo is not None:
        left_dt = left_dt.astimezone(timezone.utc)
        right_dt = right_dt.astimezone(timezone.utc)
    return abs((left_dt - right_dt).total_seconds()) / 60.0
