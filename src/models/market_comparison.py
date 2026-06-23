from __future__ import annotations

from typing import Any

import pandas as pd

from src.models.market_baseline import convert_decimal_odds_to_implied_probs, remove_vig_basic


NO_BETTING_RECOMMENDATION_WARNING = "Market gaps are diagnostic context only, not a betting recommendation."


def calculate_implied_probs_from_match_odds(home_odds: Any, draw_odds: Any, away_odds: Any) -> dict[str, float | None]:
    probs = remove_vig_basic(convert_decimal_odds_to_implied_probs(home_odds, draw_odds, away_odds))
    if any(p is None for p in probs):
        return {"market_home_prob": None, "market_draw_prob": None, "market_away_prob": None}
    return {
        "market_home_prob": float(probs[0]),  # type: ignore[arg-type]
        "market_draw_prob": float(probs[1]),  # type: ignore[arg-type]
        "market_away_prob": float(probs[2]),  # type: ignore[arg-type]
    }


def _to_float(value: Any) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) else None


def calculate_total_market_gap(model_over_2_5_prob: float, over_odds: Any, under_odds: Any) -> dict[str, float | None]:
    probs = remove_vig_basic(convert_decimal_odds_to_implied_probs(over_odds, under_odds))
    if any(p is None for p in probs):
        return {"market_over_2_5_prob": None, "market_under_2_5_prob": None, "total_market_gap": None}
    market_over = float(probs[0])  # type: ignore[arg-type]
    return {
        "market_over_2_5_prob": market_over,
        "market_under_2_5_prob": float(probs[1]),  # type: ignore[arg-type]
        "total_market_gap": round(float(model_over_2_5_prob) - market_over, 4),
    }


def compare_model_to_market(model_projection: dict[str, Any], market_row: pd.Series | dict[str, Any] | None) -> dict[str, Any]:
    row = market_row if market_row is not None else {}
    market = calculate_implied_probs_from_match_odds(
        row.get("home_odds_close") if hasattr(row, "get") else None,
        row.get("draw_odds_close") if hasattr(row, "get") else None,
        row.get("away_odds_close") if hasattr(row, "get") else None,
    )
    result: dict[str, Any] = {
        "model_home_prob": float(model_projection.get("home_win_prob", 0)),
        "model_draw_prob": float(model_projection.get("draw_prob", 0)),
        "model_away_prob": float(model_projection.get("away_win_prob", 0)),
        **market,
        "warning": NO_BETTING_RECOMMENDATION_WARNING,
    }
    if any(result[key] is None for key in ["market_home_prob", "market_draw_prob", "market_away_prob"]):
        result.update({
            "home_prob_gap": None,
            "draw_prob_gap": None,
            "away_prob_gap": None,
            "largest_gap_side": None,
            "largest_gap_value": None,
        })
    else:
        gaps = {
            "home": round(result["model_home_prob"] - result["market_home_prob"], 4),
            "draw": round(result["model_draw_prob"] - result["market_draw_prob"], 4),
            "away": round(result["model_away_prob"] - result["market_away_prob"], 4),
        }
        largest = max(gaps, key=lambda side: abs(gaps[side]))
        result.update({
            "home_prob_gap": gaps["home"],
            "draw_prob_gap": gaps["draw"],
            "away_prob_gap": gaps["away"],
            "largest_gap_side": largest,
            "largest_gap_value": gaps[largest],
        })
    result.update(calculate_total_market_gap(
        float(model_projection.get("over_2_5_prob", 0)),
        row.get("over_2_5_odds_close") if hasattr(row, "get") else None,
        row.get("under_2_5_odds_close") if hasattr(row, "get") else None,
    ))
    return result


def summarize_market_gap(comparison: dict[str, Any]) -> str:
    if comparison.get("largest_gap_side") is None:
        return "No usable 1X2 market odds for comparison. Market gaps are diagnostic context only, not a betting recommendation."
    total = comparison.get("total_market_gap")
    total_text = "" if total is None else f"; model over 2.5 gap {float(total):+.3f}"
    return (
        f"Largest model-market probability gap: {comparison['largest_gap_side']} "
        f"{float(comparison['largest_gap_value']):+.3f}{total_text}. "
        "Market gaps are diagnostic context only, not a betting recommendation."
    )


def market_row_for_projection(data: pd.DataFrame, home_team: str, away_team: str, as_of_date: str) -> pd.Series | None:
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    prior = frame[frame["date"] < pd.to_datetime(as_of_date)].sort_values("date")
    exact = prior[prior["home_team"].eq(home_team) & prior["away_team"].eq(away_team)]
    if not exact.empty:
        return exact.iloc[-1]
    related = prior[prior["home_team"].eq(home_team) | prior["away_team"].eq(home_team) | prior["home_team"].eq(away_team) | prior["away_team"].eq(away_team)]
    return related.iloc[-1] if not related.empty else None

