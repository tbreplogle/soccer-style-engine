from __future__ import annotations

from typing import Any

import pandas as pd


IDENTITY_RULES = {
    "Defensive Low Block": {
        "positive": ["defensive_block_height", "xg_against", "field_tilt_pct"],
        "summary": "deep defensive posture with limited territory and chance suppression signals",
    },
    "Possession Controller": {
        "positive": ["possession_pct", "field_tilt_pct", "avg_possession_length", "pass_completion_pct"],
        "summary": "sustained possession and territory control",
    },
    "Fast / Vertical Run Threat": {
        "positive": ["direct_speed", "progressive_passes", "runs_behind_proxy", "fast_attack_count"],
        "summary": "quick forward progress and run-threat proxies",
    },
    "High Press Chaos": {
        "positive": ["pressures", "high_regains", "ppda_proxy", "defensive_block_height"],
        "summary": "frequent pressure and high regain activity",
    },
    "Counterattacking Side": {
        "positive": ["fast_attack_count", "direct_speed", "possession_pct"],
        "summary": "lower control with faster attack creation",
    },
    "Wide Crossing / Width Side": {
        "positive": ["width_in_possession", "box_entries"],
        "summary": "width and box-entry signals",
    },
    "Slow Buildup": {
        "positive": ["avg_possession_length", "direct_speed"],
        "summary": "longer possessions and lower directness",
    },
    "Set-Piece Reliant": {
        "positive": ["set_piece_xg_for", "xg_for"],
        "summary": "large share of xG from set pieces",
    },
    "High-Line Risk Team": {
        "positive": ["defensive_block_height", "xg_against", "turnovers_own_third"],
        "summary": "higher defensive posture with exposure signals",
    },
}


def _profile_value(profile: dict[str, Any] | pd.Series, metric: str) -> float:
    if isinstance(profile, pd.Series):
        return float(profile.get(metric, 0) or 0)
    raw = profile.get("raw_metrics", profile)
    value = raw.get(metric, 0)
    return float(value) if pd.notna(value) else 0.0


def _pct(profile: dict[str, Any] | pd.Series, metric: str) -> float:
    if isinstance(profile, pd.Series):
        return float(profile.get(f"{metric}_pctile", 50) or 50)
    return float(profile.get("percentile_ranks", {}).get(metric, 50) or 50)


def _evidence(profile: dict[str, Any] | pd.Series, metrics: list[str], high_metrics: set[str]) -> list[str]:
    items = []
    for metric in metrics:
        value = _profile_value(profile, metric)
        pct = _pct(profile, metric)
        direction = "high" if metric in high_metrics else "low"
        if (direction == "high" and pct >= 60) or (direction == "low" and pct <= 40):
            items.append(f"{metric}={value:.2f}, percentile={pct:.1f}")
    return items


def classify_team_identity(profile: dict[str, Any] | pd.Series) -> dict[str, Any]:
    """Classify style identity from measured rolling metrics only."""
    low_block = _pct(profile, "defensive_block_height") <= 35 and _pct(profile, "possession_pct") <= 45
    possession = _pct(profile, "possession_pct") >= 70 and _pct(profile, "field_tilt_pct") >= 65
    vertical = _pct(profile, "direct_speed") >= 70 and (_pct(profile, "progressive_passes") >= 60 or _pct(profile, "runs_behind_proxy") >= 60)
    press = _pct(profile, "pressures") >= 70 or (_pct(profile, "high_regains") >= 70 and _pct(profile, "ppda_proxy") <= 45)
    set_piece_share = _profile_value(profile, "set_piece_xg_for") / max(0.01, _profile_value(profile, "xg_for"))
    high_line_risk = _pct(profile, "defensive_block_height") >= 75 and (_pct(profile, "xg_against") >= 65 or _pct(profile, "turnovers_own_third") >= 65)
    width = _pct(profile, "width_in_possession") >= 70 or _pct(profile, "box_entries") >= 70
    slow = _pct(profile, "avg_possession_length") >= 70 and _pct(profile, "direct_speed") <= 45
    counter = _pct(profile, "fast_attack_count") >= 65 and _pct(profile, "possession_pct") <= 50

    candidates: list[tuple[str, float, list[str], list[str]]] = []
    if low_block:
        candidates.append(("Defensive Low Block", 78, _evidence(profile, ["defensive_block_height", "possession_pct", "xg_against"], {"xg_against"}), ["Limited 360 data can blur true block shape."]))
    if possession:
        candidates.append(("Possession Controller", 80, _evidence(profile, ["possession_pct", "field_tilt_pct", "avg_possession_length"], {"possession_pct", "field_tilt_pct", "avg_possession_length"}), ["Possession can be sterile if box entries and xG are low."]))
    if vertical:
        candidates.append(("Fast / Vertical Run Threat", 76, _evidence(profile, ["direct_speed", "progressive_passes", "runs_behind_proxy", "fast_attack_count"], {"direct_speed", "progressive_passes", "runs_behind_proxy", "fast_attack_count"}), ["Runs-behind is an event-only proxy without tracking."]))
    if press:
        candidates.append(("High Press Chaos", 74, _evidence(profile, ["pressures", "high_regains", "ppda_proxy"], {"pressures", "high_regains"}), ["PPDA is a proxy from event counts."]))
    if counter:
        candidates.append(("Counterattacking Side", 70, _evidence(profile, ["fast_attack_count", "direct_speed", "possession_pct"], {"fast_attack_count", "direct_speed"}), ["Counterattacking intent needs video/scouting confirmation."]))
    if width:
        candidates.append(("Wide Crossing / Width Side", 66, _evidence(profile, ["width_in_possession", "box_entries"], {"width_in_possession", "box_entries"}), ["Width is null unless 360 is available; box entries are only a proxy."]))
    if slow:
        candidates.append(("Slow Buildup", 68, _evidence(profile, ["avg_possession_length", "direct_speed"], {"avg_possession_length"}), ["Slow tempo does not guarantee control."]))
    if set_piece_share >= 0.35 and _profile_value(profile, "set_piece_xg_for") >= 0.15:
        candidates.append(("Set-Piece Reliant", 72, [f"set_piece_xg_share={set_piece_share:.2f}"], ["Small xG samples can inflate set-piece share."]))
    if high_line_risk:
        candidates.append(("High-Line Risk Team", 70, _evidence(profile, ["defensive_block_height", "xg_against", "turnovers_own_third"], {"defensive_block_height", "xg_against", "turnovers_own_third"}), ["Line height from events is not full tracking."]))
    if not candidates:
        candidates.append(("Balanced / Mixed", 55, ["No identity threshold clearly separated from the dataset."], ["More real matches may reveal a sharper identity."]))

    matches_used = int(profile.get("matches_used", 0) if isinstance(profile, dict) else profile.get("matches_used", 0))
    quality = str(profile.get("data_quality_summary", "") if isinstance(profile, dict) else profile.get("data_quality_summary", ""))
    if matches_used < 5:
        candidates = [(name, min(score, 58), ev, cf + ["Fewer than 5 prior matches: low confidence guardrail."]) for name, score, ev, cf in candidates]
    warning = "360/tracking missing or incomplete; off-ball claims are proxy-only." if "event_only" in quality or "no_prior" in quality else ""

    identities = []
    for name, score, evidence, conflicts in sorted(candidates, key=lambda x: x[1], reverse=True):
        identities.append({
            "label": name,
            "confidence": int(score),
            "supporting_metric_evidence": evidence,
            "conflicting_evidence": conflicts,
            "data_quality_warning": warning,
        })
    return {"team": profile.get("team", "") if isinstance(profile, dict) else profile.get("team", ""), "identities": identities}
