from __future__ import annotations

from typing import Any


def normalize_neutral_site(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "neutral"}:
        return "true"
    if text in {"false", "0", "no", "home"}:
        return "false"
    return "unknown"


def international_home_advantage(neutral_site: Any, tournament_host: bool = False) -> tuple[float, list[str]]:
    neutral = normalize_neutral_site(neutral_site)
    warnings: list[str] = []
    if neutral == "true":
        return (0.0 + (0.05 if tournament_host else 0.0)), warnings
    if neutral == "false":
        return (0.10 + (0.05 if tournament_host else 0.0)), warnings
    warnings.append("neutral_site_unknown")
    return (0.04 + (0.05 if tournament_host else 0.0)), warnings


def match_weight(match_stage: Any) -> float:
    text = str(match_stage).lower()
    if "friendly" in text:
        return 0.75
    if "qualif" in text:
        return 1.05
    if any(token in text for token in ["final", "semi", "quarter", "group", "round"]):
        return 1.15
    return 1.0

