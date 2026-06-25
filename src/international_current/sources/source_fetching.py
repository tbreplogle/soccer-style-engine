from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


FETCH_STATUSES = {
    "success",
    "partial_success",
    "skipped",
    "blocked",
    "not_found",
    "parse_error",
    "parse_error_or_low_coverage",
    "empty",
    "stale_cache",
    "cache_hit",
    "cache_miss",
}


USER_AGENT = "soccer-style-engine/0.1 (+local source audit; no login; no aggressive retry)"


@dataclass
class FetchResult:
    source_name: str
    source_url: str = ""
    status: str = "skipped"
    http_status: int | None = None
    raw_path: str = ""
    metadata_path: str = ""
    fetched_at: str = ""
    parser_version: str = "phase28_v1"
    row_count: int = 0
    error_message: str = ""
    diagnostic_path: str = ""

    def __post_init__(self) -> None:
        if self.status not in FETCH_STATUSES:
            raise ValueError(f"Unsupported fetch status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_name(text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    slug = "".join(char if char.isalnum() else "_" for char in text.lower()).strip("_")
    return f"{slug[:42]}_{digest}"


def metadata_path_for(raw_path: Path) -> Path:
    return raw_path.with_suffix(raw_path.suffix + ".metadata.json")


def write_fetch_metadata(result: FetchResult, row_count: int | None = None) -> FetchResult:
    if row_count is not None:
        result.row_count = row_count
    meta_path = Path(result.metadata_path) if result.metadata_path else metadata_path_for(Path(result.raw_path))
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    result.metadata_path = str(meta_path)
    meta_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return result


def read_local_source(source_name: str, path: str | Path) -> tuple[FetchResult, str]:
    target = Path(path)
    if not target.exists():
        result = FetchResult(
            source_name=source_name,
            source_url=str(target),
            status="cache_miss",
            raw_path=str(target),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            error_message="Local source file not found.",
        )
        return write_fetch_metadata(result), ""
    text = target.read_text(encoding="utf-8", errors="replace")
    result = FetchResult(
        source_name=source_name,
        source_url=str(target),
        status="cache_hit" if text.strip() else "empty",
        raw_path=str(target),
        fetched_at=datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc).isoformat(),
    )
    return write_fetch_metadata(result), text


def fetch_public_source(
    *,
    source_name: str,
    source_url: str,
    raw_dir: str | Path,
    allow_network: bool = False,
    timeout_seconds: int = 8,
) -> tuple[FetchResult, str]:
    raw_root = Path(raw_dir)
    raw_root.mkdir(parents=True, exist_ok=True)
    suffix = Path(source_url.split("?", 1)[0]).suffix or ".html"
    raw_path = raw_root / f"{_safe_name(source_name + '_' + source_url)}{suffix}"
    metadata_path = metadata_path_for(raw_path)
    fetched_at = datetime.now(timezone.utc).isoformat()
    if not allow_network:
        if raw_path.exists():
            text = raw_path.read_text(encoding="utf-8", errors="replace")
            return write_fetch_metadata(FetchResult(
                source_name=source_name,
                source_url=source_url,
                status="cache_hit" if text.strip() else "empty",
                raw_path=str(raw_path),
                metadata_path=str(metadata_path),
                fetched_at=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=timezone.utc).isoformat(),
            )), text
        return write_fetch_metadata(FetchResult(
            source_name=source_name,
            source_url=source_url,
            status="cache_miss",
            raw_path=str(raw_path),
            metadata_path=str(metadata_path),
            fetched_at=fetched_at,
            error_message="Network disabled and raw cache not found.",
        )), ""

    request = Request(source_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json,text/csv,*/*"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status_code = int(getattr(response, "status", 200) or 200)
            body = response.read()
            text = body.decode("utf-8", errors="replace")
            raw_path.write_text(text, encoding="utf-8")
            status = "success" if text.strip() else "empty"
            return write_fetch_metadata(FetchResult(
                source_name=source_name,
                source_url=source_url,
                status=status,
                http_status=status_code,
                raw_path=str(raw_path),
                metadata_path=str(metadata_path),
                fetched_at=fetched_at,
            )), text
    except HTTPError as exc:
        status = "blocked" if exc.code in {401, 403, 429} else "not_found" if exc.code == 404 else "skipped"
        return write_fetch_metadata(FetchResult(
            source_name=source_name,
            source_url=source_url,
            status=status,
            http_status=exc.code,
            raw_path=str(raw_path),
            metadata_path=str(metadata_path),
            fetched_at=fetched_at,
            error_message=str(exc),
        )), ""
    except (TimeoutError, URLError, OSError) as exc:
        return write_fetch_metadata(FetchResult(
            source_name=source_name,
            source_url=source_url,
            status="blocked" if "timed out" in str(exc).lower() else "skipped",
            raw_path=str(raw_path),
            metadata_path=str(metadata_path),
            fetched_at=fetched_at,
            error_message=str(exc),
        )), ""
