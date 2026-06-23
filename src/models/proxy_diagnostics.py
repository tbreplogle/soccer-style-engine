from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.features.free_style_proxies import _scale, _team_rows
from src.models.current_score_projection import PROXY_GROUPS, _proxy_adjustment
from src.models.score_projection import _projection_from_xg

REQUIRED_METRICS = [
    "home_goals_mae",
    "away_goals_mae",
    "total_goals_mae",
    "wdl_log_loss",
    "brier_score",
    "exact_score_hit_rate",
    "over_under_2_5_accuracy",
    "calibration_summary",
    "lift_vs_baseline_total_mae",
]


@dataclass(frozen=True)
class ProxyDiagnosticConfig:
    config_name: str
    cap: float
    enabled_proxy_groups: tuple[str, ...]


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def _log_loss(home_goals: float, away_goals: float, probs: dict[str, Any]) -> float:
    key = "home_win_prob" if home_goals > away_goals else "away_win_prob" if away_goals > home_goals else "draw_prob"
    return float(-np.log(max(1e-9, float(probs[key]))))


def _brier(home_goals: float, away_goals: float, probs: dict[str, Any]) -> float:
    actual = np.array([home_goals > away_goals, home_goals == away_goals, home_goals < away_goals], dtype=float)
    pred = np.array([probs["home_win_prob"], probs["draw_prob"], probs["away_win_prob"]], dtype=float)
    return float(np.mean((pred - actual) ** 2))


def _calibration_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "no rows"
    frame = pd.DataFrame(rows)
    bins = pd.cut(frame["home_win_prob"], bins=[0, 0.25, 0.5, 0.75, 1.0], include_lowest=True)
    table = frame.assign(prob_bin=bins, home_win_actual=(frame["home_goals"] > frame["away_goals"]).astype(float))
    grouped = table.groupby("prob_bin", observed=False).agg(avg_prob=("home_win_prob", "mean"), actual=("home_win_actual", "mean"), matches=("match_id", "count"))
    parts = []
    for idx, row in grouped.reset_index().iterrows():
        if row["matches"] > 0:
            parts.append(f"{row['prob_bin']}: p={row['avg_prob']:.2f}, actual={row['actual']:.2f}, n={int(row['matches'])}")
    return "; ".join(parts) if parts else "no populated bins"


def _configs(caps: list[float]) -> list[ProxyDiagnosticConfig]:
    configs = [ProxyDiagnosticConfig("baseline_only", 0.0, tuple())]
    for cap in caps:
        configs.append(ProxyDiagnosticConfig(f"all_proxies_cap_{cap:g}", cap, tuple(PROXY_GROUPS)))
        if cap > 0:
            for group in PROXY_GROUPS:
                configs.append(ProxyDiagnosticConfig(f"only_{group}_cap_{cap:g}", cap, (group,)))
            for group in PROXY_GROUPS:
                groups = tuple(g for g in PROXY_GROUPS if g != group)
                configs.append(ProxyDiagnosticConfig(f"without_{group}_cap_{cap:g}", cap, groups))
    # Preserve order while removing duplicate baseline from cap 0 if present.
    seen = set()
    unique = []
    for config in configs:
        key = (config.config_name, config.cap, config.enabled_proxy_groups)
        if key not in seen:
            unique.append(config)
            seen.add(key)
    return unique


def _baseline_from_proxy_rows(
    home_team: str,
    away_team: str,
    home_proxy: dict[str, Any],
    away_proxy: dict[str, Any],
) -> tuple[float, float]:
    def value(row: dict[str, Any], key: str, default: float) -> float:
        raw = row.get(key, default)
        return float(raw) if pd.notna(raw) else default

    league_avg = np.nanmean([
        value(home_proxy, "goals_for_per_match", np.nan),
        value(home_proxy, "goals_against_per_match", np.nan),
        value(away_proxy, "goals_for_per_match", np.nan),
        value(away_proxy, "goals_against_per_match", np.nan),
    ])
    league_avg = 1.25 if pd.isna(league_avg) else max(0.2, float(league_avg))
    home_attack = value(home_proxy, "goals_for_per_match", league_avg)
    away_attack = value(away_proxy, "goals_for_per_match", league_avg)
    home_def = value(home_proxy, "goals_against_per_match", league_avg)
    away_def = value(away_proxy, "goals_against_per_match", league_avg)
    return (
        round(max(0.15, 0.58 * home_attack + 0.42 * away_def + 0.12), 4),
        round(max(0.15, 0.58 * away_attack + 0.42 * home_def - 0.06), 4),
    )


def _match_context(
    data: pd.DataFrame,
    window: pd.DataFrame,
    proxy_cache: dict[pd.Timestamp, pd.DataFrame],
    team_rows: pd.DataFrame,
    teams: list[str],
) -> pd.DataFrame:
    contexts = []
    for _, match in window.iterrows():
        as_of = match["date"].normalize()
        if as_of not in proxy_cache:
            proxies = _fast_proxy_snapshot(team_rows, teams, as_of)
            proxy_cache[as_of] = proxies.set_index("team") if not proxies.empty else pd.DataFrame()
        lookup = proxy_cache[as_of]
        home_proxy = lookup.loc[match["home_team"]].to_dict() if not lookup.empty and match["home_team"] in lookup.index else {"recent_matches_used": 0}
        away_proxy = lookup.loc[match["away_team"]].to_dict() if not lookup.empty and match["away_team"] in lookup.index else {"recent_matches_used": 0}
        home_xg_base, away_xg_base = _baseline_from_proxy_rows(match["home_team"], match["away_team"], home_proxy, away_proxy)
        contexts.append({
            "match_id": match["match_id"],
            "date": as_of.date().isoformat(),
            "home_team": match["home_team"],
            "away_team": match["away_team"],
            "home_goals": float(match["home_goals"]),
            "away_goals": float(match["away_goals"]),
            "home_xg_base": float(home_xg_base),
            "away_xg_base": float(away_xg_base),
            "home_proxy": home_proxy,
            "away_proxy": away_proxy,
        })
    return pd.DataFrame(contexts)


def _project_context(row: dict[str, Any], config: ProxyDiagnosticConfig) -> dict[str, Any]:
    home_proxy = row["home_proxy"]
    away_proxy = row["away_proxy"]
    home_adj, _ = _proxy_adjustment(home_proxy, away_proxy, enabled_proxy_groups=set(config.enabled_proxy_groups), total_cap=config.cap)
    away_adj, _ = _proxy_adjustment(away_proxy, home_proxy, enabled_proxy_groups=set(config.enabled_proxy_groups), total_cap=config.cap)
    home_xg = max(0.05, float(row["home_xg_base"]) + home_adj)
    away_xg = max(0.05, float(row["away_xg_base"]) + away_adj)
    probs = _projection_from_xg(home_xg, away_xg)
    return {
        "match_id": row["match_id"],
        "date": row["date"],
        "home_team": row["home_team"],
        "away_team": row["away_team"],
        "home_goals": row["home_goals"],
        "away_goals": row["away_goals"],
        "home_xg": home_xg,
        "away_xg": away_xg,
        "home_adj": home_adj,
        "away_adj": away_adj,
        **probs,
    }


def _summarize_predictions(predictions: list[dict[str, Any]], baseline_total_mae: float, window_name: str, config: ProxyDiagnosticConfig) -> dict[str, Any]:
    if not predictions:
        return {
            "window": window_name,
            "config_name": config.config_name,
            "cap": config.cap,
            "enabled_proxy_groups": ",".join(config.enabled_proxy_groups),
            "matches": 0,
            **{metric: np.nan for metric in REQUIRED_METRICS},
        }
    home_errors = []
    away_errors = []
    total_errors = []
    losses = []
    briers = []
    exact_hits = []
    ou_hits = []
    for pred in predictions:
        home_errors.append(abs(pred["home_xg"] - pred["home_goals"]))
        away_errors.append(abs(pred["away_xg"] - pred["away_goals"]))
        total_errors.append(abs((pred["home_xg"] + pred["away_xg"]) - (pred["home_goals"] + pred["away_goals"])))
        losses.append(_log_loss(pred["home_goals"], pred["away_goals"], pred))
        briers.append(_brier(pred["home_goals"], pred["away_goals"], pred))
        exact_hits.append(round(pred["home_xg"]) == pred["home_goals"] and round(pred["away_xg"]) == pred["away_goals"])
        ou_hits.append((pred["over_2_5_prob"] >= 0.5) == ((pred["home_goals"] + pred["away_goals"]) > 2.5))
    total_mae = float(np.mean(total_errors))
    return {
        "window": window_name,
        "config_name": config.config_name,
        "cap": config.cap,
        "enabled_proxy_groups": ",".join(config.enabled_proxy_groups),
        "matches": int(len(predictions)),
        "home_goals_mae": float(np.mean(home_errors)),
        "away_goals_mae": float(np.mean(away_errors)),
        "total_goals_mae": total_mae,
        "wdl_log_loss": float(np.mean(losses)),
        "brier_score": float(np.mean(briers)),
        "exact_score_hit_rate": float(np.mean(exact_hits)),
        "over_under_2_5_accuracy": float(np.mean(ou_hits)),
        "calibration_summary": _calibration_summary(predictions),
        "lift_vs_baseline_total_mae": float(baseline_total_mae - total_mae),
    }


def _build_windows(data: pd.DataFrame, start_date: str, end_date: str, min_matches: int, include_breakdowns: bool = False) -> list[tuple[str, pd.DataFrame]]:
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    custom = data[(data["date"] >= start) & (data["date"] <= end)].sort_values("date")
    windows: list[tuple[str, pd.DataFrame]] = [("custom", custom)]
    if not include_breakdowns:
        return windows
    for period, rows in custom.groupby(custom["date"].dt.to_period("M")):
        if len(rows) >= min_matches:
            windows.append((f"month_{period}", rows.sort_values("date")))
    # Rolling 30-day windows, sampled at month starts to keep diagnostics practical.
    for anchor in pd.date_range(start=start, end=end, freq="MS"):
        stop = anchor + pd.Timedelta(days=29)
        rows = custom[(custom["date"] >= anchor) & (custom["date"] <= stop)]
        if len(rows) >= min_matches:
            windows.append((f"rolling_30d_{anchor.date()}", rows.sort_values("date")))
    return windows


def _weighted_mean(series: pd.Series, weights: np.ndarray) -> float:
    vals = pd.to_numeric(series, errors="coerce")
    mask = vals.notna()
    if not mask.any():
        return float("nan")
    return float(np.average(vals[mask], weights=weights[mask.to_numpy()]))


def _fast_proxy_snapshot(team_rows: pd.DataFrame, teams: list[str], as_of: pd.Timestamp, recent_matches: int = 8, decay: float = 0.85) -> pd.DataFrame:
    history = team_rows[team_rows["date"] < as_of]
    rows: list[dict[str, Any]] = []
    for team in teams:
        team_history = history[history["team"].eq(team)].sort_values("date").tail(recent_matches)
        weights = np.power(decay, np.arange(len(team_history) - 1, -1, -1)) if not team_history.empty else np.array([])
        row: dict[str, Any] = {"team": team, "recent_matches_used": int(len(team_history))}
        for metric in ["goals_for", "goals_against", "shots_for", "shots_against", "sot_for", "sot_against", "corners_for", "corners_against", "total_shots", "total_corners", "points", "market_implied_strength", "total_goals", "total_cards_fouls", "yellow_cards", "red_cards"]:
            row[f"{metric}_per_match"] = _weighted_mean(team_history[metric], weights) if not team_history.empty and metric in team_history else float("nan")
        row["shot_share"] = row["shots_for_per_match"] / max(0.01, row["shots_for_per_match"] + row["shots_against_per_match"]) if pd.notna(row["shots_for_per_match"]) else float("nan")
        row["corner_share"] = row["corners_for_per_match"] / max(0.01, row["corners_for_per_match"] + row["corners_against_per_match"]) if pd.notna(row["corners_for_per_match"]) else float("nan")
        row["goals_per_shot"] = row["goals_for_per_match"] / max(0.01, row["shots_for_per_match"]) if pd.notna(row["shots_for_per_match"]) else float("nan")
        row["goals_per_sot"] = row["goals_for_per_match"] / max(0.01, row["sot_for_per_match"]) if pd.notna(row["sot_for_per_match"]) else float("nan")
        row["sot_rate"] = row["sot_for_per_match"] / max(0.01, row["shots_for_per_match"]) if pd.notna(row["shots_for_per_match"]) else float("nan")
        rows.append(row)
    r = pd.DataFrame(rows)
    if r.empty:
        return r
    r["control_proxy"] = (0.45 * _scale(r["shot_share"]) + 0.35 * _scale(r["corner_share"]) + 0.20 * _scale(r["market_implied_strength_per_match"]))
    r["attacking_pressure_proxy"] = (0.35 * _scale(r["shots_for_per_match"]) + 0.30 * _scale(r["sot_for_per_match"]) + 0.20 * _scale(r["corners_for_per_match"]) + 0.15 * _scale(r["goals_for_per_match"]))
    r["defensive_shell_proxy"] = (0.30 * _scale(r["shots_against_per_match"], inverse=True) + 0.30 * _scale(r["sot_against_per_match"], inverse=True) + 0.25 * _scale(r["goals_against_per_match"], inverse=True) + 0.15 * _scale(r["total_shots_per_match"], inverse=True))
    r["tempo_proxy"] = (0.35 * _scale(r["total_shots_per_match"]) + 0.25 * _scale(r["total_corners_per_match"]) + 0.25 * _scale(r["total_goals_per_match"]) + 0.15 * _scale(r["total_cards_fouls_per_match"]))
    r["chaos_proxy"] = (0.45 * _scale(r["total_cards_fouls_per_match"]) + 0.25 * _scale(r["red_cards_per_match"]) + 0.15 * _scale(r["total_goals_per_match"]) + 0.15 * _scale((r["shots_for_per_match"] - r["shots_against_per_match"]).abs()))
    r["finishing_proxy"] = (0.55 * _scale(r["goals_per_shot"]) + 0.45 * _scale(r["goals_per_sot"]))
    r["chance_quality_proxy"] = (0.60 * _scale(r["sot_rate"]) + 0.40 * _scale(r["goals_per_shot"]))
    r["directness_proxy"] = (0.55 * r["attacking_pressure_proxy"] + 0.45 * (100 - r["control_proxy"])).clip(0, 100)
    r["under_profile_proxy"] = (0.35 * _scale(r["total_shots_per_match"], inverse=True) + 0.30 * _scale(r["total_goals_per_match"], inverse=True) + 0.20 * _scale(r["sot_against_per_match"], inverse=True) + 0.15 * (100 - r["tempo_proxy"]))
    r["data_quality_flags"] = r.apply(lambda row: "low_sample" if row["recent_matches_used"] < 6 else "proxy_basic_match_stats", axis=1)
    return r


def recommend_proxy_policy(results: pd.DataFrame, min_matches: int = 50) -> str:
    custom = results[results["window"].eq("custom")]
    if custom.empty or custom["matches"].max() < min_matches:
        return "needs_more_data"
    non_baseline = results[~results["config_name"].eq("baseline_only")].copy()
    if non_baseline.empty:
        return "needs_more_data"
    window_lifts = non_baseline.groupby("window")["lift_vs_baseline_total_mae"].max()
    positive_share = float((window_lifts > 0.01).mean()) if len(window_lifts) else 0
    near_or_negative_share = float((window_lifts <= 0.01).mean()) if len(window_lifts) else 1
    best_custom = non_baseline.loc[non_baseline["window"].eq("custom")].sort_values("lift_vs_baseline_total_mae", ascending=False).head(1)
    if near_or_negative_share >= 0.6:
        return "disable_proxy_adjustments"
    if positive_share < 0.5:
        return "use_proxy_adjustments_context_only"
    if not best_custom.empty:
        groups = [g for g in str(best_custom.iloc[0]["enabled_proxy_groups"]).split(",") if g]
        if 0 < len(groups) <= 2 and best_custom.iloc[0]["cap"] <= 0.05:
            return "use_proxy_adjustments_low_cap"
    return "use_proxy_adjustments_context_only"


def write_diagnostics_report(results: pd.DataFrame, recommendation: str, output_path: str | Path) -> str:
    best = results.sort_values("lift_vs_baseline_total_mae", ascending=False).head(10)
    custom = results[results["window"].eq("custom")].sort_values("lift_vs_baseline_total_mae", ascending=False).head(10)
    def table(df: pd.DataFrame, columns: list[str]) -> str:
        if df.empty:
            return "_No rows._"
        shown = df[columns].copy()
        lines = [
            "| " + " | ".join(columns) + " |",
            "| " + " | ".join(["---"] * len(columns)) + " |",
        ]
        for _, row in shown.iterrows():
            values = []
            for col in columns:
                value = row[col]
                values.append(f"{value:.4f}" if isinstance(value, float) else str(value))
            lines.append("| " + " | ".join(values) + " |")
        return "\n".join(lines)

    lines = [
        "# Proxy Diagnostics Summary",
        "",
        "This report evaluates free_proxy_style score adjustments. It is not a betting report and does not claim true event/tracking style.",
        "",
        f"Recommendation: `{recommendation}`",
        "",
        "## Best Overall Configs",
        "",
        table(best, ["window", "config_name", "cap", "matches", "total_goals_mae", "lift_vs_baseline_total_mae"]),
        "",
        "## Best Custom-Window Configs",
        "",
        table(custom, ["config_name", "cap", "matches", "total_goals_mae", "lift_vs_baseline_total_mae"]),
        "",
        "## Guardrail",
        "",
        "If lift is negative or unstable, proxy explanations may remain useful, but xG score adjustments should stay disabled or low-cap.",
        "",
    ]
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report


def run_proxy_diagnostics(
    matches: pd.DataFrame | str | Path,
    start_date: str,
    end_date: str,
    caps: list[float] | None = None,
    min_matches: int = 6,
    output_dir: str | Path = "outputs/reports",
    include_breakdowns: bool = False,
) -> dict[str, Any]:
    data = _load(matches)
    caps = [0.0, 0.03, 0.05, 0.08, 0.12, 0.20] if caps is None else caps
    configs = _configs(caps)
    summaries = []
    proxy_cache: dict[pd.Timestamp, pd.DataFrame] = {}
    team_rows = _team_rows(data)
    teams = sorted(set(data["home_team"].dropna()).union(set(data["away_team"].dropna())))
    for window_name, window in _build_windows(data, start_date, end_date, min_matches, include_breakdowns=include_breakdowns):
        if len(window) < min_matches:
            continue
        contexts = _match_context(data, window, proxy_cache, team_rows, teams).to_dict("records")
        baseline_config = ProxyDiagnosticConfig("baseline_only", 0.0, tuple())
        baseline_predictions = [_project_context(row, baseline_config) for row in contexts]
        baseline_total_mae = float(np.mean([abs((pred["home_xg"] + pred["away_xg"]) - (pred["home_goals"] + pred["away_goals"])) for pred in baseline_predictions])) if baseline_predictions else np.nan
        for config in configs:
            predictions = [_project_context(row, config) for row in contexts]
            summaries.append(_summarize_predictions(predictions, baseline_total_mae, window_name, config))
    results = pd.DataFrame(summaries)
    recommendation = recommend_proxy_policy(results, min_matches=max(25, min_matches))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results_path = output / "proxy_diagnostics_results.csv"
    summary_path = output / "proxy_diagnostics_summary.md"
    results.to_csv(results_path, index=False)
    report = write_diagnostics_report(results, recommendation, summary_path)
    return {
        "results": results,
        "recommendation": recommendation,
        "report": report,
        "results_path": results_path,
        "summary_path": summary_path,
    }
