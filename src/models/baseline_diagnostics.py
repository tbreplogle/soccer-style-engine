from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.models.market_baseline import BASELINE_MODES, estimate_current_baseline_xg
from src.features.free_style_proxies import _team_rows
from src.models.proxy_diagnostics import _fast_proxy_snapshot
from src.models.market_baseline import estimate_market_home_away_strength, estimate_market_total_pressure_from_ou25
from src.models.score_projection import _projection_from_xg

BASELINE_REQUIRED_METRICS = [
    "home_goals_mae",
    "away_goals_mae",
    "total_goals_mae",
    "wdl_log_loss",
    "brier_score",
    "exact_score_hit_rate",
    "over_under_2_5_accuracy",
    "calibration_table",
    "mean_projected_total",
    "mean_actual_total",
    "home_win_calibration",
    "draw_calibration",
    "away_win_calibration",
]


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def _log_loss(row: dict[str, Any]) -> float:
    key = "home_win_prob" if row["home_goals"] > row["away_goals"] else "away_win_prob" if row["away_goals"] > row["home_goals"] else "draw_prob"
    return float(-np.log(max(1e-9, row[key])))


def _brier(row: dict[str, Any]) -> float:
    actual = np.array([row["home_goals"] > row["away_goals"], row["home_goals"] == row["away_goals"], row["home_goals"] < row["away_goals"]], dtype=float)
    pred = np.array([row["home_win_prob"], row["draw_prob"], row["away_win_prob"]], dtype=float)
    return float(np.mean((pred - actual) ** 2))


def _calibration(rows: list[dict[str, Any]], prob_col: str, actual_fn) -> str:
    if not rows:
        return "no rows"
    df = pd.DataFrame(rows)
    return f"avg_prob={df[prob_col].mean():.3f}; actual={df.apply(actual_fn, axis=1).mean():.3f}; n={len(df)}"


def _summarize(rows: list[dict[str, Any]], mode: str, window_name: str) -> dict[str, Any]:
    if not rows:
        return {"window": window_name, "baseline_mode": mode, "matches": 0, **{m: np.nan for m in BASELINE_REQUIRED_METRICS}}
    home_errors = [abs(r["home_xg"] - r["home_goals"]) for r in rows]
    away_errors = [abs(r["away_xg"] - r["away_goals"]) for r in rows]
    total_errors = [abs((r["home_xg"] + r["away_xg"]) - (r["home_goals"] + r["away_goals"])) for r in rows]
    exact = [round(r["home_xg"]) == r["home_goals"] and round(r["away_xg"]) == r["away_goals"] for r in rows]
    ou = [(r["over_2_5_prob"] >= 0.5) == ((r["home_goals"] + r["away_goals"]) > 2.5) for r in rows]
    projected_totals = [r["home_xg"] + r["away_xg"] for r in rows]
    actual_totals = [r["home_goals"] + r["away_goals"] for r in rows]
    return {
        "window": window_name,
        "baseline_mode": mode,
        "matches": len(rows),
        "home_goals_mae": float(np.mean(home_errors)),
        "away_goals_mae": float(np.mean(away_errors)),
        "total_goals_mae": float(np.mean(total_errors)),
        "wdl_log_loss": float(np.mean([_log_loss(r) for r in rows])),
        "brier_score": float(np.mean([_brier(r) for r in rows])),
        "exact_score_hit_rate": float(np.mean(exact)),
        "over_under_2_5_accuracy": float(np.mean(ou)),
        "calibration_table": _calibration(rows, "home_win_prob", lambda r: float(r["home_goals"] > r["away_goals"])),
        "mean_projected_total": float(np.mean(projected_totals)),
        "mean_actual_total": float(np.mean(actual_totals)),
        "home_win_calibration": _calibration(rows, "home_win_prob", lambda r: float(r["home_goals"] > r["away_goals"])),
        "draw_calibration": _calibration(rows, "draw_prob", lambda r: float(r["home_goals"] == r["away_goals"])),
        "away_win_calibration": _calibration(rows, "away_win_prob", lambda r: float(r["home_goals"] < r["away_goals"])),
    }


def _windows(data: pd.DataFrame, start_date: str, end_date: str, min_matches: int, monthly: bool) -> list[tuple[str, pd.DataFrame]]:
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    custom = data[(data["date"] >= start) & (data["date"] <= end)].sort_values("date")
    out = [("custom", custom)]
    if monthly:
        for period, rows in custom.groupby(custom["date"].dt.to_period("M")):
            if len(rows) >= min_matches:
                out.append((f"month_{period}", rows.sort_values("date")))
    return out


def _value(row: dict[str, Any], key: str, default: float) -> float:
    raw = row.get(key, default)
    return float(raw) if pd.notna(raw) else default


def _goals_from_context(home_proxy: dict[str, Any], away_proxy: dict[str, Any]) -> tuple[float, float, int, int]:
    league_avg = np.nanmean([
        _value(home_proxy, "goals_for_per_match", np.nan),
        _value(home_proxy, "goals_against_per_match", np.nan),
        _value(away_proxy, "goals_for_per_match", np.nan),
        _value(away_proxy, "goals_against_per_match", np.nan),
    ])
    league_avg = 1.25 if pd.isna(league_avg) else max(0.2, float(league_avg))
    home_xg = 0.58 * _value(home_proxy, "goals_for_per_match", league_avg) + 0.42 * _value(away_proxy, "goals_against_per_match", league_avg) + 0.12
    away_xg = 0.58 * _value(away_proxy, "goals_for_per_match", league_avg) + 0.42 * _value(home_proxy, "goals_against_per_match", league_avg) - 0.06
    return round(max(0.15, home_xg), 4), round(max(0.15, away_xg), 4), int(_value(home_proxy, "recent_matches_used", 0)), int(_value(away_proxy, "recent_matches_used", 0))


def _shots_from_context(home_proxy: dict[str, Any], away_proxy: dict[str, Any], goal_home: float, goal_away: float) -> tuple[float, float, bool]:
    required = ["shots_for_per_match", "sot_for_per_match", "shots_against_per_match", "sot_against_per_match"]
    if any(pd.isna(home_proxy.get(k)) or pd.isna(away_proxy.get(k)) for k in required):
        return goal_home, goal_away, False
    # Conservative conversion rates from current snapshot; kept bounded.
    g_per_shot = np.nanmean([
        _value(home_proxy, "goals_for_per_match", 1.2) / max(1, _value(home_proxy, "shots_for_per_match", 10)),
        _value(away_proxy, "goals_for_per_match", 1.2) / max(1, _value(away_proxy, "shots_for_per_match", 10)),
    ])
    g_per_sot = np.nanmean([
        _value(home_proxy, "goals_for_per_match", 1.2) / max(1, _value(home_proxy, "sot_for_per_match", 4)),
        _value(away_proxy, "goals_for_per_match", 1.2) / max(1, _value(away_proxy, "sot_for_per_match", 4)),
    ])
    g_per_shot = min(0.16, max(0.06, float(g_per_shot)))
    g_per_sot = min(0.45, max(0.18, float(g_per_sot)))
    home_attack = 0.55 * _value(home_proxy, "shots_for_per_match", 10) * g_per_shot + 0.45 * _value(home_proxy, "sot_for_per_match", 4) * g_per_sot
    away_attack = 0.55 * _value(away_proxy, "shots_for_per_match", 10) * g_per_shot + 0.45 * _value(away_proxy, "sot_for_per_match", 4) * g_per_sot
    home_allowed = 0.55 * _value(away_proxy, "shots_against_per_match", 10) * g_per_shot + 0.45 * _value(away_proxy, "sot_against_per_match", 4) * g_per_sot
    away_allowed = 0.55 * _value(home_proxy, "shots_against_per_match", 10) * g_per_shot + 0.45 * _value(home_proxy, "sot_against_per_match", 4) * g_per_sot
    return round(max(0.15, 0.55 * home_attack + 0.45 * home_allowed + 0.08), 4), round(max(0.15, 0.55 * away_attack + 0.45 * away_allowed - 0.04), 4), True


def _baseline_for_match(mode: str, match: pd.Series, home_proxy: dict[str, Any], away_proxy: dict[str, Any]) -> tuple[float, float]:
    goals_home, goals_away, _, _ = _goals_from_context(home_proxy, away_proxy)
    shots_home, shots_away, shots_ok = _shots_from_context(home_proxy, away_proxy, goals_home, goals_away)
    market = estimate_market_home_away_strength(match.get("home_odds_close"), match.get("draw_odds_close"), match.get("away_odds_close"))
    total_pressure = estimate_market_total_pressure_from_ou25(match.get("over_2_5_odds_close"), match.get("under_2_5_odds_close"))
    if mode == "goals":
        return goals_home, goals_away
    if mode == "shots":
        return shots_home, shots_away
    if mode == "market" and market["home_strength_share"] is not None:
        total = goals_home + goals_away
        share = 0.65 * (goals_home / max(0.01, total)) + 0.35 * float(market["home_strength_share"])
        return round(max(0.15, total * share), 4), round(max(0.15, total * (1 - share)), 4)
    if mode == "totals_market" and total_pressure["total_pressure"] is not None:
        base_total = goals_home + goals_away
        market_total = max(1.0, base_total + float(total_pressure["total_pressure"]) * 1.25)
        blended_total = 0.65 * base_total + 0.35 * market_total
        share = goals_home / max(0.01, base_total)
        return round(max(0.15, blended_total * share), 4), round(max(0.15, blended_total * (1 - share)), 4)
    if mode == "blended":
        components = {"goals": (goals_home, goals_away)}
        weights = {"goals": 0.45}
        if shots_ok:
            components["shots"] = (shots_home, shots_away); weights["shots"] = 0.25
        if market["home_strength_share"] is not None:
            components["market"] = _baseline_for_match("market", match, home_proxy, away_proxy); weights["market"] = 0.20
        if total_pressure["total_pressure"] is not None:
            components["totals_market"] = _baseline_for_match("totals_market", match, home_proxy, away_proxy); weights["totals_market"] = 0.10
        total_weight = sum(weights.values())
        home = sum(components[k][0] * weights[k] for k in components) / total_weight
        away = sum(components[k][1] * weights[k] for k in components) / total_weight
        return round(max(0.15, home), 4), round(max(0.15, away), 4)
    return goals_home, goals_away


def run_baseline_diagnostics(
    matches: pd.DataFrame | str | Path,
    start_date: str,
    end_date: str,
    baseline_modes: list[str] | None = None,
    min_matches: int = 6,
    monthly: bool = False,
    output_dir: str | Path = "outputs/reports",
    league: str | None = None,
) -> dict[str, Any]:
    data = _load(matches)
    if league and "league" in data.columns:
        data = data[data["league"].eq(league)].copy()
    modes = [m for m in (baseline_modes or BASELINE_MODES) if m in BASELINE_MODES]
    summaries = []
    team_rows = _team_rows(data)
    teams = sorted(set(data["home_team"].dropna()).union(set(data["away_team"].dropna())))
    proxy_cache: dict[pd.Timestamp, pd.DataFrame] = {}
    for window_name, window in _windows(data, start_date, end_date, min_matches, monthly):
        if len(window) < min_matches:
            continue
        for mode in modes:
            rows = []
            for _, match in window.iterrows():
                as_of = match["date"].date().isoformat()
                key = match["date"].normalize()
                if key not in proxy_cache:
                    proxy_cache[key] = _fast_proxy_snapshot(team_rows, teams, key).set_index("team")
                lookup = proxy_cache[key]
                home_proxy = lookup.loc[match["home_team"]].to_dict() if match["home_team"] in lookup.index else {"recent_matches_used": 0}
                away_proxy = lookup.loc[match["away_team"]].to_dict() if match["away_team"] in lookup.index else {"recent_matches_used": 0}
                if _value(home_proxy, "recent_matches_used", 0) < min_matches or _value(away_proxy, "recent_matches_used", 0) < min_matches:
                    continue
                home_xg, away_xg = _baseline_for_match(mode, match, home_proxy, away_proxy)
                probs = _projection_from_xg(home_xg, away_xg)
                rows.append({
                    "match_id": match["match_id"],
                    "home_team": match["home_team"],
                    "away_team": match["away_team"],
                    "home_goals": float(match["home_goals"]),
                    "away_goals": float(match["away_goals"]),
                    "home_xg": float(home_xg),
                    "away_xg": float(away_xg),
                    **probs,
                })
            summaries.append(_summarize(rows, mode, window_name))
    columns = ["window", "baseline_mode", "matches", *BASELINE_REQUIRED_METRICS]
    results = pd.DataFrame(summaries, columns=columns)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results_path = output / "baseline_diagnostics_results.csv"
    summary_path = output / "baseline_diagnostics_summary.md"
    results.to_csv(results_path, index=False)
    report = write_baseline_diagnostics_report(results, summary_path)
    return {"results": results, "report": report, "results_path": results_path, "summary_path": summary_path}


def write_baseline_diagnostics_report(results: pd.DataFrame, output_path: str | Path) -> str:
    custom = results[results["window"].eq("custom")].sort_values("total_goals_mae")
    best = custom.head(1)
    lines = [
        "# Baseline Diagnostics Summary",
        "",
        "This report compares transparent current-score baselines. Proxy score adjustments remain disabled.",
        "",
        "## Custom Window Results",
        "",
        _table(custom, ["baseline_mode", "matches", "home_goals_mae", "away_goals_mae", "total_goals_mae", "wdl_log_loss", "brier_score", "over_under_2_5_accuracy"]),
        "",
        "## Recommendation",
        "",
        f"Best total-goals MAE baseline: `{best.iloc[0]['baseline_mode']}`." if not best.empty else "No eligible baseline result.",
        "",
    ]
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report


def _table(df: pd.DataFrame, columns: list[str]) -> str:
    if df.empty:
        return "_No rows._"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in df[columns].iterrows():
        vals = [f"{row[c]:.4f}" if isinstance(row[c], float) else str(row[c]) for c in columns]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)
