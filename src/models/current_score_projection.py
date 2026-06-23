from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.features.free_style_proxies import build_free_style_proxies
from src.models.market_baseline import BASELINE_MODES, estimate_current_baseline_xg
from src.models.market_comparison import compare_model_to_market, market_row_for_projection, summarize_market_gap
from src.models.projection_confidence import score_projection_confidence
from src.models.score_projection import _projection_from_xg

INDIVIDUAL_PROXY_ADJUSTMENT_CAP = 0.08
TOTAL_PROXY_ADJUSTMENT_CAP = 0.20
DEFAULT_PROXY_ADJUSTMENT_CAP = 0.0
PROXY_GROUPS = [
    "control_proxy",
    "attacking_pressure_proxy",
    "defensive_shell_proxy",
    "tempo_proxy",
    "chaos_proxy",
    "finishing_proxy",
    "chance_quality_proxy",
    "directness_proxy",
    "under_profile_proxy",
]
PROJECTION_PROFILES = ["score_projection", "winner_probability", "total_goals", "market_anchored", "model_only"]


def _has_market_odds(row: pd.Series | None) -> bool:
    if row is None:
        return False
    return all(pd.notna(pd.to_numeric(row.get(col), errors="coerce")) for col in ["home_odds_close", "draw_odds_close", "away_odds_close"])


def _has_totals_odds(row: pd.Series | None) -> bool:
    if row is None:
        return False
    return all(pd.notna(pd.to_numeric(row.get(col), errors="coerce")) for col in ["over_2_5_odds_close", "under_2_5_odds_close"])


def resolve_projection_profile_baseline(
    projection_profile: str = "score_projection",
    baseline_mode: str | None = None,
    market_odds_available: bool = False,
    totals_odds_available: bool = False,
) -> tuple[str, str]:
    profile = projection_profile if projection_profile in PROJECTION_PROFILES else "score_projection"
    if baseline_mode in BASELINE_MODES:
        return profile, str(baseline_mode)
    if profile == "winner_probability":
        return profile, "market" if market_odds_available else "blended"
    if profile == "total_goals":
        return profile, "totals_market" if totals_odds_available else "goals"
    if profile == "market_anchored":
        return profile, "market" if market_odds_available else "blended"
    if profile == "model_only":
        return profile, "blended"
    return profile, "blended"


def _market_influence_level(profile: str, mode: str, odds_available: bool, totals_available: bool) -> str:
    if profile == "model_only" or mode in {"goals", "shots"}:
        return "None"
    if profile == "market_anchored" and odds_available:
        return "High"
    if mode == "market" and odds_available:
        return "Medium"
    if mode == "totals_market" and totals_available:
        return "Medium"
    if mode == "blended" and (odds_available or totals_available):
        return "Low"
    return "None"


def _cap(value: float, cap: float) -> float:
    return max(-cap, min(cap, value))


def _proxy_adjustment(
    team: pd.Series,
    opponent: pd.Series,
    enabled_proxy_groups: set[str] | None = None,
    individual_cap: float = INDIVIDUAL_PROXY_ADJUSTMENT_CAP,
    total_cap: float = DEFAULT_PROXY_ADJUSTMENT_CAP,
) -> tuple[float, list[str]]:
    enabled = set(PROXY_GROUPS) if enabled_proxy_groups is None else set(enabled_proxy_groups)
    adjustments: list[tuple[float, str, str]] = []
    if "attacking_pressure_proxy" in enabled and team.get("attacking_pressure_proxy", 50) - opponent.get("defensive_shell_proxy", 50) >= 15:
        adjustments.append((0.06, "attacking_pressure_proxy", "attacking_pressure_proxy over opponent defensive_shell_proxy"))
    if "control_proxy" in enabled and team.get("control_proxy", 50) - opponent.get("control_proxy", 50) >= 18:
        adjustments.append((0.04, "control_proxy", "control_proxy edge from shots/corners/odds"))
    if "under_profile_proxy" in enabled and (team.get("under_profile_proxy", 50) >= 70 or opponent.get("under_profile_proxy", 50) >= 70):
        adjustments.append((-0.05, "under_profile_proxy", "under_profile_proxy suppresses total chance volume"))
    if "finishing_proxy" in enabled and team.get("finishing_proxy", 50) >= 75:
        adjustments.append((0.03, "finishing_proxy", "finishing_proxy is high but unstable"))
    if "tempo_proxy" in enabled and team.get("tempo_proxy", 50) >= 70 and opponent.get("under_profile_proxy", 50) < 65:
        adjustments.append((0.03, "tempo_proxy", "tempo_proxy points to higher match volume"))
    if "chaos_proxy" in enabled and team.get("chaos_proxy", 50) >= 75:
        adjustments.append((0.02, "chaos_proxy", "chaos_proxy adds volatility but is weak evidence"))
    if "chance_quality_proxy" in enabled and team.get("chance_quality_proxy", 50) - opponent.get("defensive_shell_proxy", 50) >= 12:
        adjustments.append((0.03, "chance_quality_proxy", "chance_quality_proxy over opponent defensive shell"))
    if "directness_proxy" in enabled and team.get("directness_proxy", 50) >= 70 and opponent.get("defensive_shell_proxy", 50) < 60:
        adjustments.append((0.025, "directness_proxy", "directness_proxy against non-shell profile"))
    if "defensive_shell_proxy" in enabled and opponent.get("defensive_shell_proxy", 50) >= 75:
        adjustments.append((-0.035, "defensive_shell_proxy", "opponent defensive_shell_proxy suppresses xG"))
    clipped = [(_cap(v, individual_cap), group, reason) for v, group, reason in adjustments]
    total = _cap(sum(value for value, _, _ in clipped), total_cap)
    if int(team.get("recent_matches_used", 0)) < 6 or int(opponent.get("recent_matches_used", 0)) < 6:
        total *= 0.5
    return round(total, 4), [reason for _, _, reason in clipped]


def project_current_match(
    matches: pd.DataFrame | str | Path,
    home_team: str,
    away_team: str,
    as_of_date: str,
    league: str | None = None,
    neutral_site: bool = False,
    output_path: str | Path | None = None,
    enable_proxy_adjustments: bool = False,
    proxy_total_cap: float | None = None,
    enabled_proxy_groups: set[str] | list[str] | None = None,
    baseline_mode: str | None = None,
    projection_profile: str = "score_projection",
) -> pd.DataFrame:
    data = matches.copy() if isinstance(matches, pd.DataFrame) else pd.read_csv(matches)
    if league:
        data = data[data["league"].eq(league)]
    market_row = market_row_for_projection(data, home_team, away_team, as_of_date)
    odds_available = _has_market_odds(market_row)
    totals_available = _has_totals_odds(market_row)
    profile, mode = resolve_projection_profile_baseline(
        projection_profile=projection_profile,
        baseline_mode=baseline_mode,
        market_odds_available=odds_available,
        totals_odds_available=totals_available,
    )
    market_enabled = profile != "model_only"
    blend_weights = {"goals": 0.65, "shots": 0.35, "market": 0.0, "totals_market": 0.0} if profile == "model_only" and mode == "blended" else None
    baseline = estimate_current_baseline_xg(
        data,
        home_team,
        away_team,
        as_of_date,
        baseline_mode=mode,
        neutral_site=neutral_site,
        blend_weights=blend_weights,
        market_enabled=market_enabled,
    )
    baselines = {
        candidate: estimate_current_baseline_xg(
            data,
            home_team,
            away_team,
            as_of_date,
            baseline_mode=candidate,
            neutral_site=neutral_site,
            market_enabled=market_enabled,
        )
        for candidate in BASELINE_MODES
    }
    if profile == "market_anchored" and mode == "market" and baselines["market"].get("available", True):
        goals_base = baselines["goals"]
        market_base = baselines["market"]
        baseline = {
            **market_base,
            "home_xg_base": round(0.35 * float(goals_base["home_xg_base"]) + 0.65 * float(market_base["home_xg_base"]), 4),
            "away_xg_base": round(0.35 * float(goals_base["away_xg_base"]) + 0.65 * float(market_base["away_xg_base"]), 4),
            "baseline_mode": "market",
            "market_anchor_weight": 0.65,
        }
    proxies = build_free_style_proxies(data, as_of_date)
    lookup = proxies.set_index("team")
    home = lookup.loc[home_team] if home_team in lookup.index else pd.Series({"recent_matches_used": 0})
    away = lookup.loc[away_team] if away_team in lookup.index else pd.Series({"recent_matches_used": 0})
    total_cap = proxy_total_cap if proxy_total_cap is not None else (TOTAL_PROXY_ADJUSTMENT_CAP if enable_proxy_adjustments else DEFAULT_PROXY_ADJUSTMENT_CAP)
    groups = set(enabled_proxy_groups) if enabled_proxy_groups is not None else None
    home_adj, home_reasons = _proxy_adjustment(home, away, enabled_proxy_groups=groups, total_cap=total_cap)
    away_adj, away_reasons = _proxy_adjustment(away, home, enabled_proxy_groups=groups, total_cap=total_cap)
    home_final = max(0.05, float(baseline["home_xg_base"]) + home_adj)
    away_final = max(0.05, float(baseline["away_xg_base"]) + away_adj)
    probs = _projection_from_xg(home_final, away_final)
    market_gap = compare_model_to_market(probs, market_row if market_enabled else None)
    confidence = score_projection_confidence(
        data,
        baseline,
        baselines,
        market_gap,
        proxy_adjustments_enabled=total_cap > 0,
        projection_profile=profile,
    )
    low_conf = int(baseline["home_prior_matches"]) < 6 or int(baseline["away_prior_matches"]) < 6
    warnings = ["free_proxy_style is not true event/tracking style"]
    if total_cap == 0:
        warnings.append("Proxy explanations are shown, but proxy score adjustments are disabled by default pending diagnostics.")
    if low_conf:
        warnings.append("Fewer than 6 prior matches; proxy adjustments halved.")
    row: dict[str, Any] = {
        "date": as_of_date,
        "as_of_date": as_of_date,
        "home_team": home_team,
        "away_team": away_team,
        "projection_profile": profile,
        "home_xg_base": baseline["home_xg_base"],
        "away_xg_base": baseline["away_xg_base"],
        "baseline_mode": baseline["baseline_mode"],
        "baseline_mode_used": baseline["baseline_mode"],
        "market_influence_level": _market_influence_level(profile, mode, odds_available, totals_available),
        "home_xg_proxy_adjustment": home_adj,
        "away_xg_proxy_adjustment": away_adj,
        "home_xg_final": round(home_final, 4),
        "away_xg_final": round(away_final, 4),
        **probs,
        "confidence": confidence["confidence_label"],
        "confidence_score": confidence["confidence_score"],
        "confidence_label": confidence["confidence_label"],
        "confidence_reasons": confidence["confidence_reasons"],
        "risk_flags": confidence["risk_flags"],
        "disagreement_flags": confidence["disagreement_flags"],
        "data_mode": "free_proxy_style",
        "data_quality_flags": "low_sample" if low_conf else "proxy_basic_match_stats",
        "proxy_style_explanation": "; ".join(home_reasons + away_reasons) or "No strong proxy-style adjustment.",
        "market_gap_summary": summarize_market_gap(market_gap),
        "model_market_gap_summary": summarize_market_gap(market_gap),
        "betting_recommendation": None,
        "warnings": " | ".join(warnings),
    }
    result = pd.DataFrame([row])
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
    return result


def proxy_adjustments_are_capped(matches: pd.DataFrame | str | Path, home_team: str, away_team: str, as_of_date: str) -> bool:
    row = project_current_match(matches, home_team, away_team, as_of_date, enable_proxy_adjustments=True).iloc[0]
    return abs(row["home_xg_proxy_adjustment"]) <= TOTAL_PROXY_ADJUSTMENT_CAP and abs(row["away_xg_proxy_adjustment"]) <= TOTAL_PROXY_ADJUSTMENT_CAP
