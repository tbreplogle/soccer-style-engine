from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.models.score_projection import _poisson_probs


PROFILES = ["score_projection", "winner_probability", "total_goals", "market_anchored", "model_only"]
VALIDATION_COLUMNS = [
    "league",
    "league_name",
    "season_code",
    "season_label",
    "window",
    "projection_profile",
    "matches",
    "home_goals_mae",
    "away_goals_mae",
    "total_goals_mae",
    "wdl_log_loss",
    "brier_score",
    "exact_score_hit_rate",
    "over_under_2_5_accuracy",
    "mean_projected_total",
    "mean_actual_total",
    "calibration_gap",
    "confidence_bucket_performance",
    "high_bucket_count",
    "medium_bucket_count",
    "low_bucket_count",
    "profile_disagreement_rate",
    "market_model_disagreement_rate",
]


def _load(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    out = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def _num(value: Any, default: float = np.nan) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) else default


def _log_loss(row: dict[str, Any]) -> float:
    key = "home_win_prob" if row["home_goals"] > row["away_goals"] else "away_win_prob" if row["away_goals"] > row["home_goals"] else "draw_prob"
    return float(-np.log(max(1e-9, float(row[key]))))


def _brier(row: dict[str, Any]) -> float:
    actual = np.array([row["home_goals"] > row["away_goals"], row["home_goals"] == row["away_goals"], row["home_goals"] < row["away_goals"]], dtype=float)
    pred = np.array([row["home_win_prob"], row["draw_prob"], row["away_win_prob"]], dtype=float)
    return float(np.mean((pred - actual) ** 2))


def _market_share(row: pd.Series) -> float | None:
    odds = [_num(row.get("home_odds_close")), _num(row.get("draw_odds_close")), _num(row.get("away_odds_close"))]
    if any(pd.isna(v) or v <= 1 for v in odds):
        return None
    probs = [1 / v for v in odds]
    total = sum(probs)
    decisive = probs[0] + probs[2]
    return float((probs[0] / total) / max(0.01, decisive / total))


def _confidence(prior_home: int, prior_away: int, has_odds: bool, disagreement: float) -> str:
    if prior_home < 6 or prior_away < 6:
        return "Low"
    score = 62 + (8 if prior_home >= 10 and prior_away >= 10 else 0) + (4 if has_odds else -4) - (10 if disagreement > 0.35 else 0)
    return "High" if score >= 75 else "Medium" if score >= 50 else "Low"


def _fast_projection_from_xg(home_xg: float, away_xg: float) -> dict[str, Any]:
    home_probs = _poisson_probs(home_xg, max_goals=8)
    away_probs = _poisson_probs(away_xg, max_goals=8)
    matrix = np.outer(home_probs, away_probs)
    home_goals = np.arange(matrix.shape[0])[:, None]
    away_goals = np.arange(matrix.shape[1])[None, :]
    totals = home_goals + away_goals
    most_idx = np.unravel_index(np.argmax(matrix), matrix.shape)
    return {
        "most_likely_score": f"{int(most_idx[0])}-{int(most_idx[1])}",
        "projected_total": round(home_xg + away_xg, 4),
        "home_win_prob": float(matrix[home_goals > away_goals].sum()),
        "draw_prob": float(matrix[home_goals == away_goals].sum()),
        "away_win_prob": float(matrix[home_goals < away_goals].sum()),
        "over_1_5_prob": float(matrix[totals > 1.5].sum()),
        "over_2_5_prob": float(matrix[totals > 2.5].sum()),
        "under_2_5_prob": float(matrix[totals < 2.5].sum()),
        "btts_prob": float(matrix[(home_goals > 0) & (away_goals > 0)].sum()),
    }


def _team_stats(prior: pd.DataFrame, team: str) -> dict[str, float]:
    home = prior[prior["home_team"].eq(team)]
    away = prior[prior["away_team"].eq(team)]
    gf = list(pd.to_numeric(home["home_goals"], errors="coerce").dropna()) + list(pd.to_numeric(away["away_goals"], errors="coerce").dropna())
    ga = list(pd.to_numeric(home["away_goals"], errors="coerce").dropna()) + list(pd.to_numeric(away["home_goals"], errors="coerce").dropna())
    shots = list(pd.to_numeric(home.get("home_shots", pd.Series(dtype=float)), errors="coerce").dropna()) + list(pd.to_numeric(away.get("away_shots", pd.Series(dtype=float)), errors="coerce").dropna())
    sot = list(pd.to_numeric(home.get("home_shots_on_target", pd.Series(dtype=float)), errors="coerce").dropna()) + list(pd.to_numeric(away.get("away_shots_on_target", pd.Series(dtype=float)), errors="coerce").dropna())
    return {
        "matches": len(gf),
        "gf": float(np.mean(gf)) if gf else np.nan,
        "ga": float(np.mean(ga)) if ga else np.nan,
        "shots": float(np.mean(shots)) if shots else np.nan,
        "sot": float(np.mean(sot)) if sot else np.nan,
    }


def _empty_stats() -> dict[str, float]:
    return {"matches": 0, "gf": np.nan, "ga": np.nan, "shots": np.nan, "sot": np.nan}


def _build_prior_contexts(group: pd.DataFrame) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    stats: dict[str, dict[str, float]] = {}
    goals_sum = 0.0
    goals_n = 0

    def current(team: str) -> dict[str, float]:
        row = stats.get(team)
        if not row or row["matches"] <= 0:
            return _empty_stats()
        return {
            "matches": int(row["matches"]),
            "gf": row["gf_sum"] / row["matches"],
            "ga": row["ga_sum"] / row["matches"],
            "shots": row["shots_sum"] / row["shots_n"] if row["shots_n"] else np.nan,
            "sot": row["sot_sum"] / row["sot_n"] if row["sot_n"] else np.nan,
        }

    def update(team: str, gf: Any, ga: Any, shots: Any, sot: Any) -> None:
        row = stats.setdefault(team, {"matches": 0, "gf_sum": 0.0, "ga_sum": 0.0, "shots_sum": 0.0, "shots_n": 0, "sot_sum": 0.0, "sot_n": 0})
        gf_value = _num(gf)
        ga_value = _num(ga)
        if pd.notna(gf_value) and pd.notna(ga_value):
            row["matches"] += 1
            row["gf_sum"] += gf_value
            row["ga_sum"] += ga_value
        shot_value = _num(shots)
        if pd.notna(shot_value):
            row["shots_sum"] += shot_value
            row["shots_n"] += 1
        sot_value = _num(sot)
        if pd.notna(sot_value):
            row["sot_sum"] += sot_value
            row["sot_n"] += 1

    for _, match in group.iterrows():
        contexts.append({
            "league_avg": goals_sum / goals_n if goals_n else np.nan,
            "home": current(match["home_team"]),
            "away": current(match["away_team"]),
            "prior_rows": goals_n // 2,
        })
        home_goals = _num(match.get("home_goals"))
        away_goals = _num(match.get("away_goals"))
        if pd.notna(home_goals) and pd.notna(away_goals):
            goals_sum += home_goals + away_goals
            goals_n += 2
        update(match["home_team"], home_goals, away_goals, match.get("home_shots"), match.get("home_shots_on_target"))
        update(match["away_team"], away_goals, home_goals, match.get("away_shots"), match.get("away_shots_on_target"))
    return contexts


def _project_match(group: pd.DataFrame, idx: int, profile: str, contexts: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    match = group.iloc[idx]
    context = contexts[idx] if contexts is not None and idx < len(contexts) else None
    if ((context and context.get("prior_rows", 0) < 2) or (context is None and idx < 2)) or pd.isna(match["home_goals"]) or pd.isna(match["away_goals"]):
        return None
    prior = group.iloc[:idx] if context is None else None
    league_avg = float(context["league_avg"]) if context is not None else float(pd.to_numeric(pd.concat([prior["home_goals"], prior["away_goals"]]), errors="coerce").mean())
    league_avg = league_avg if pd.notna(league_avg) else 1.25
    home = context["home"] if context is not None else _team_stats(prior, match["home_team"])
    away = context["away"] if context is not None else _team_stats(prior, match["away_team"])
    ha = 0.12
    home_goals_xg = 0.58 * (home["gf"] if pd.notna(home["gf"]) else league_avg) + 0.42 * (away["ga"] if pd.notna(away["ga"]) else league_avg) + ha
    away_goals_xg = 0.58 * (away["gf"] if pd.notna(away["gf"]) else league_avg) + 0.42 * (home["ga"] if pd.notna(home["ga"]) else league_avg) - ha / 2
    home_shots_xg, away_shots_xg = home_goals_xg, away_goals_xg
    if pd.notna(home["shots"]) and pd.notna(away["shots"]):
        home_shots_xg = 0.75 * home_goals_xg + 0.25 * max(0.2, home["shots"] / 9.5)
        away_shots_xg = 0.75 * away_goals_xg + 0.25 * max(0.2, away["shots"] / 9.5)
    market = _market_share(match)
    if market is not None:
        total = home_goals_xg + away_goals_xg
        home_market_xg = total * (0.65 * (home_goals_xg / max(0.01, total)) + 0.35 * market)
        away_market_xg = total - home_market_xg
    else:
        home_market_xg, away_market_xg = home_goals_xg, away_goals_xg
    if profile == "winner_probability":
        hxg, axg = home_market_xg, away_market_xg
    elif profile == "total_goals":
        hxg, axg = home_goals_xg * 1.02, away_goals_xg * 1.02
    elif profile == "market_anchored":
        hxg, axg = 0.35 * home_goals_xg + 0.65 * home_market_xg, 0.35 * away_goals_xg + 0.65 * away_market_xg
    elif profile == "model_only":
        hxg, axg = 0.65 * home_goals_xg + 0.35 * home_shots_xg, 0.65 * away_goals_xg + 0.35 * away_shots_xg
    else:
        hxg, axg = 0.45 * home_goals_xg + 0.25 * home_shots_xg + 0.20 * home_market_xg + 0.10 * home_goals_xg, 0.45 * away_goals_xg + 0.25 * away_shots_xg + 0.20 * away_market_xg + 0.10 * away_goals_xg
    disagreement = abs((home_market_xg + away_market_xg) - (home_goals_xg + away_goals_xg))
    probs = _fast_projection_from_xg(max(0.05, hxg), max(0.05, axg))
    return {
        "match_id": match.get("match_id", f"{match['home_team']}-{match['away_team']}-{match['date']}"),
        "date": match["date"],
        "home_team": match["home_team"],
        "away_team": match["away_team"],
        "home_goals": float(match["home_goals"]),
        "away_goals": float(match["away_goals"]),
        "home_xg": float(max(0.05, hxg)),
        "away_xg": float(max(0.05, axg)),
        "confidence_label": _confidence(int(home["matches"]), int(away["matches"]), market is not None, disagreement),
        "profile_disagreement": disagreement > 0.35,
        "market_model_disagreement": market is not None and abs(home_market_xg - home_goals_xg) > 0.25,
        **probs,
    }


def _summarize(rows: list[dict[str, Any]], meta: dict[str, Any], profile: str, window: str) -> dict[str, Any]:
    if not rows:
        return {**meta, "window": window, "projection_profile": profile, "matches": 0, **{c: np.nan for c in VALIDATION_COLUMNS if c not in meta and c not in {"window", "projection_profile", "matches"}}}
    totals = [r["home_goals"] + r["away_goals"] for r in rows]
    projected = [r["home_xg"] + r["away_xg"] for r in rows]
    exact = [round(r["home_xg"]) == r["home_goals"] and round(r["away_xg"]) == r["away_goals"] for r in rows]
    ou = [(r["over_2_5_prob"] >= 0.5) == ((r["home_goals"] + r["away_goals"]) > 2.5) for r in rows]
    buckets = []
    for label in ["High", "Medium", "Low"]:
        bucket = [r for r in rows if r["confidence_label"] == label]
        if bucket:
            bucket_mae = np.mean([abs((r["home_xg"] + r["away_xg"]) - (r["home_goals"] + r["away_goals"])) for r in bucket])
            buckets.append(f"{label}: n={len(bucket)}, total_mae={bucket_mae:.3f}")
    return {
        **meta,
        "window": window,
        "projection_profile": profile,
        "matches": len(rows),
        "home_goals_mae": float(np.mean([abs(r["home_xg"] - r["home_goals"]) for r in rows])),
        "away_goals_mae": float(np.mean([abs(r["away_xg"] - r["away_goals"]) for r in rows])),
        "total_goals_mae": float(np.mean([abs(p - a) for p, a in zip(projected, totals)])),
        "wdl_log_loss": float(np.mean([_log_loss(r) for r in rows])),
        "brier_score": float(np.mean([_brier(r) for r in rows])),
        "exact_score_hit_rate": float(np.mean(exact)),
        "over_under_2_5_accuracy": float(np.mean(ou)),
        "mean_projected_total": float(np.mean(projected)),
        "mean_actual_total": float(np.mean(totals)),
        "calibration_gap": float(np.mean([r["home_win_prob"] for r in rows]) - np.mean([r["home_goals"] > r["away_goals"] for r in rows])),
        "confidence_bucket_performance": "; ".join(buckets) if buckets else "no populated confidence buckets",
        "high_bucket_count": sum(1 for r in rows if r["confidence_label"] == "High"),
        "medium_bucket_count": sum(1 for r in rows if r["confidence_label"] == "Medium"),
        "low_bucket_count": sum(1 for r in rows if r["confidence_label"] == "Low"),
        "profile_disagreement_rate": float(np.mean([r["profile_disagreement"] for r in rows])),
        "market_model_disagreement_rate": float(np.mean([r["market_model_disagreement"] for r in rows])),
    }


def run_multi_season_validation(
    matches: pd.DataFrame | str | Path,
    start_date: str,
    end_date: str,
    profiles: list[str] | None = None,
    min_matches: int = 6,
    monthly: bool = False,
    by_league: bool = False,
    by_season: bool = False,
    output_dir: str | Path = "outputs/reports",
) -> dict[str, Any]:
    data = _load(matches)
    data = data[(data["date"] >= pd.to_datetime(start_date)) & (data["date"] <= pd.to_datetime(end_date))].sort_values("date")
    selected = [p for p in (profiles or PROFILES) if p in PROFILES]
    summaries = []
    group_cols = ["league", "season_code"]
    for (league, season), group in data.groupby(group_cols):
        group = group.sort_values("date").reset_index(drop=True)
        if len(group) < min_matches:
            continue
        meta = {
            "league": league,
            "league_name": group["league_name"].iloc[0] if "league_name" in group else league,
            "season_code": season,
            "season_label": group["season_label"].iloc[0] if "season_label" in group else season,
        }
        windows = [("full", group.index.tolist())]
        if monthly:
            for period, rows in group.groupby(group["date"].dt.to_period("M")):
                if len(rows) >= min_matches:
                    windows.append((f"month_{period}", rows.index.tolist()))
        contexts = _build_prior_contexts(group)
        cache: dict[tuple[int, str], dict[str, Any] | None] = {}
        for window_name, indices in windows:
            for profile in selected:
                rows = []
                for idx in indices:
                    key = (idx, profile)
                    if key not in cache:
                        cache[key] = _project_match(group, idx, profile, contexts)
                    rows.append(cache[key])
                summaries.append(_summarize([r for r in rows if r], meta, profile, window_name))
    results = pd.DataFrame(summaries, columns=VALIDATION_COLUMNS)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results_path = output / "multi_season_validation_results.csv"
    summary_path = output / "multi_season_validation_summary.md"
    results.to_csv(results_path, index=False)
    report = write_multi_season_validation_report(results, summary_path)
    return {"results": results, "report": report, "results_path": results_path, "summary_path": summary_path}


def write_multi_season_validation_report(results: pd.DataFrame, output_path: str | Path) -> str:
    full = results[(results["window"].eq("full")) & (pd.to_numeric(results["matches"], errors="coerce").fillna(0) > 0)]
    best_wdl = full.sort_values("wdl_log_loss").groupby(["league", "season_code"], as_index=False).head(1)
    best_total = full.sort_values("total_goals_mae").groupby(["league", "season_code"], as_index=False).head(1)
    profile_stability = full.groupby("projection_profile").agg(avg_log_loss=("wdl_log_loss", "mean"), avg_total_mae=("total_goals_mae", "mean"), seasons=("season_code", "nunique")).reset_index().sort_values("avg_log_loss")
    winner_wdl_share = float(best_wdl["projection_profile"].eq("winner_probability").mean()) if not best_wdl.empty else 0.0
    lines = [
        "# Multi-Season Validation Summary",
        "",
        f"Winner-probability W/D/L win share: {winner_wdl_share:.3f}",
        "Proxy score adjustments remain disabled by default.",
        "",
        "## Most Stable Profiles",
        "",
        _table(profile_stability, ["projection_profile", "avg_log_loss", "avg_total_mae", "seasons"]),
        "",
        "## Best W/D/L By League-Season",
        "",
        _table(best_wdl, ["league", "season_code", "projection_profile", "matches", "wdl_log_loss", "brier_score"]),
        "",
        "## Best Totals By League-Season",
        "",
        _table(best_total, ["league", "season_code", "projection_profile", "matches", "total_goals_mae", "over_under_2_5_accuracy"]),
        "",
    ]
    report = "\n".join(lines)
    Path(output_path).write_text(report, encoding="utf-8")
    return report


def _table(df: pd.DataFrame, columns: list[str], limit: int = 40) -> str:
    if df.empty:
        return "_No rows._"
    cols = [c for c in columns if c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df[cols].head(limit).iterrows():
        vals = [f"{row[c]:.4f}" if isinstance(row[c], float) else str(row[c]) for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)
