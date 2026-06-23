from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.features.free_style_proxies import _team_rows
from src.models.baseline_diagnostics import _baseline_for_match, _brier, _calibration, _log_loss, _table, _value
from src.models.current_score_projection import PROJECTION_PROFILES, resolve_projection_profile_baseline
from src.models.market_comparison import compare_model_to_market
from src.models.projection_confidence import score_projection_confidence
from src.models.proxy_diagnostics import _fast_proxy_snapshot
from src.models.score_projection import _projection_from_xg

PROFILE_REQUIRED_METRICS = [
    "home_goals_mae",
    "away_goals_mae",
    "total_goals_mae",
    "wdl_log_loss",
    "brier_score",
    "exact_score_hit_rate",
    "over_under_2_5_accuracy",
    "calibration_summary",
    "confidence_bucket_summary",
]


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def _has_match_odds(match: pd.Series) -> bool:
    return all(pd.notna(pd.to_numeric(match.get(col), errors="coerce")) for col in ["home_odds_close", "draw_odds_close", "away_odds_close"])


def _has_total_odds(match: pd.Series) -> bool:
    return all(pd.notna(pd.to_numeric(match.get(col), errors="coerce")) for col in ["over_2_5_odds_close", "under_2_5_odds_close"])


def _weighted_pair(pairs: list[tuple[tuple[float, float], float]]) -> tuple[float, float]:
    total_weight = sum(weight for _, weight in pairs) or 1.0
    home = sum(pair[0] * weight for pair, weight in pairs) / total_weight
    away = sum(pair[1] * weight for pair, weight in pairs) / total_weight
    return round(max(0.15, home), 4), round(max(0.15, away), 4)


def _profile_xg(profile: str, mode: str, match: pd.Series, home_proxy: dict[str, Any], away_proxy: dict[str, Any]) -> tuple[float, float]:
    if profile == "model_only" and mode == "blended":
        goals = _baseline_for_match("goals", match, home_proxy, away_proxy)
        shots = _baseline_for_match("shots", match, home_proxy, away_proxy)
        return _weighted_pair([(goals, 0.65), (shots, 0.35)])
    if profile == "market_anchored" and mode == "market" and _has_match_odds(match):
        goals = _baseline_for_match("goals", match, home_proxy, away_proxy)
        market = _baseline_for_match("market", match, home_proxy, away_proxy)
        return _weighted_pair([(goals, 0.35), (market, 0.65)])
    return _baseline_for_match(mode, match, home_proxy, away_proxy)


def _summarize_bucket(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "no rows"
    frame = pd.DataFrame(rows)
    parts = []
    for label in ["High", "Medium", "Low"]:
        bucket = frame[frame["confidence_label"].eq(label)]
        if bucket.empty:
            continue
        total_mae = np.mean(abs((bucket["home_xg"] + bucket["away_xg"]) - (bucket["home_goals"] + bucket["away_goals"])))
        log_loss = np.mean([_log_loss(row) for row in bucket.to_dict("records")])
        parts.append(f"{label}: n={len(bucket)}, total_mae={total_mae:.3f}, log_loss={log_loss:.3f}")
    return "; ".join(parts) if parts else "no populated confidence buckets"


def _summarize(rows: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    if not rows:
        return {"projection_profile": profile, "matches": 0, **{metric: np.nan for metric in PROFILE_REQUIRED_METRICS}}
    home_errors = [abs(r["home_xg"] - r["home_goals"]) for r in rows]
    away_errors = [abs(r["away_xg"] - r["away_goals"]) for r in rows]
    total_errors = [abs((r["home_xg"] + r["away_xg"]) - (r["home_goals"] + r["away_goals"])) for r in rows]
    exact = [round(r["home_xg"]) == r["home_goals"] and round(r["away_xg"]) == r["away_goals"] for r in rows]
    ou = [(r["over_2_5_prob"] >= 0.5) == ((r["home_goals"] + r["away_goals"]) > 2.5) for r in rows]
    return {
        "projection_profile": profile,
        "matches": len(rows),
        "home_goals_mae": float(np.mean(home_errors)),
        "away_goals_mae": float(np.mean(away_errors)),
        "total_goals_mae": float(np.mean(total_errors)),
        "wdl_log_loss": float(np.mean([_log_loss(r) for r in rows])),
        "brier_score": float(np.mean([_brier(r) for r in rows])),
        "exact_score_hit_rate": float(np.mean(exact)),
        "over_under_2_5_accuracy": float(np.mean(ou)),
        "calibration_summary": _calibration(rows, "home_win_prob", lambda r: float(r["home_goals"] > r["away_goals"])),
        "confidence_bucket_summary": _summarize_bucket(rows),
    }


def run_projection_profile_diagnostics(
    matches: pd.DataFrame | str | Path,
    start_date: str,
    end_date: str,
    profiles: list[str] | None = None,
    min_matches: int = 6,
    output_dir: str | Path = "outputs/reports",
) -> dict[str, Any]:
    data = _load(matches)
    selected = [profile for profile in (profiles or PROJECTION_PROFILES) if profile in PROJECTION_PROFILES]
    window = data[(data["date"] >= pd.to_datetime(start_date)) & (data["date"] <= pd.to_datetime(end_date))].sort_values("date")
    team_rows = _team_rows(data)
    teams = sorted(set(data["home_team"].dropna()).union(set(data["away_team"].dropna())))
    proxy_cache: dict[pd.Timestamp, pd.DataFrame] = {}
    summaries = []
    for profile in selected:
        rows = []
        for _, match in window.iterrows():
            key = match["date"].normalize()
            if key not in proxy_cache:
                proxy_cache[key] = _fast_proxy_snapshot(team_rows, teams, key).set_index("team")
            lookup = proxy_cache[key]
            home_proxy = lookup.loc[match["home_team"]].to_dict() if match["home_team"] in lookup.index else {"recent_matches_used": 0}
            away_proxy = lookup.loc[match["away_team"]].to_dict() if match["away_team"] in lookup.index else {"recent_matches_used": 0}
            if _value(home_proxy, "recent_matches_used", 0) < min_matches or _value(away_proxy, "recent_matches_used", 0) < min_matches:
                continue
            _, mode = resolve_projection_profile_baseline(profile, None, _has_match_odds(match), _has_total_odds(match))
            home_xg, away_xg = _profile_xg(profile, mode, match, home_proxy, away_proxy)
            probs = _projection_from_xg(home_xg, away_xg)
            market_gap = compare_model_to_market(probs, None if profile == "model_only" else match)
            baselines = {
                "goals": {"home_xg_base": _baseline_for_match("goals", match, home_proxy, away_proxy)[0], "away_xg_base": _baseline_for_match("goals", match, home_proxy, away_proxy)[1], "available": True},
                "shots": {"home_xg_base": _baseline_for_match("shots", match, home_proxy, away_proxy)[0], "away_xg_base": _baseline_for_match("shots", match, home_proxy, away_proxy)[1], "available": True},
                "market": {"home_xg_base": _baseline_for_match("market", match, home_proxy, away_proxy)[0], "away_xg_base": _baseline_for_match("market", match, home_proxy, away_proxy)[1], "available": _has_match_odds(match)},
                "totals_market": {"home_xg_base": _baseline_for_match("totals_market", match, home_proxy, away_proxy)[0], "away_xg_base": _baseline_for_match("totals_market", match, home_proxy, away_proxy)[1], "available": _has_total_odds(match)},
            }
            confidence = score_projection_confidence(
                data,
                {"baseline_mode": mode, "home_prior_matches": int(_value(home_proxy, "recent_matches_used", 0)), "away_prior_matches": int(_value(away_proxy, "recent_matches_used", 0))},
                baselines,
                market_gap,
                proxy_adjustments_enabled=False,
                projection_profile=profile,
            )
            rows.append({
                "match_id": match["match_id"],
                "home_team": match["home_team"],
                "away_team": match["away_team"],
                "home_goals": float(match["home_goals"]),
                "away_goals": float(match["away_goals"]),
                "home_xg": float(home_xg),
                "away_xg": float(away_xg),
                "confidence_label": confidence["confidence_label"],
                **probs,
            })
        summaries.append(_summarize(rows, profile))
    columns = ["projection_profile", "matches", *PROFILE_REQUIRED_METRICS]
    results = pd.DataFrame(summaries, columns=columns)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results_path = output / "projection_profile_diagnostics_results.csv"
    summary_path = output / "projection_profile_diagnostics_summary.md"
    results.to_csv(results_path, index=False)
    report = write_projection_profile_diagnostics_report(results, summary_path)
    return {"results": results, "report": report, "results_path": results_path, "summary_path": summary_path}


def write_projection_profile_diagnostics_report(results: pd.DataFrame, output_path: str | Path) -> str:
    eligible = results[results["matches"].fillna(0).astype(float) > 0]
    best_wdl = eligible.sort_values("wdl_log_loss").head(1)
    best_total = eligible.sort_values("total_goals_mae").head(1)
    lines = [
        "# Projection Profile Diagnostics Summary",
        "",
        "This report compares projection profiles. Proxy score adjustments remain disabled.",
        "",
        "## Results",
        "",
        _table(results, ["projection_profile", "matches", "home_goals_mae", "away_goals_mae", "total_goals_mae", "wdl_log_loss", "brier_score", "over_under_2_5_accuracy"]),
        "",
        "## Best Profiles",
        "",
        f"Best W/D/L log loss: `{best_wdl.iloc[0]['projection_profile']}`." if not best_wdl.empty else "No eligible W/D/L profile.",
        f"Best total-goals MAE: `{best_total.iloc[0]['projection_profile']}`." if not best_total.empty else "No eligible totals profile.",
        "",
        "## Confidence Buckets",
        "",
    ]
    for _, row in results.iterrows():
        lines.append(f"- `{row['projection_profile']}`: {row['confidence_bucket_summary']}")
    lines.append("")
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report

