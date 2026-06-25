from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd


TOTAL_LINES = (0.5, 1.5, 2.5, 3.5, 4.5)


def excel_safe_score_label(home_goals: int | float | str, away_goals: int | float | str) -> str:
    return f"{int(home_goals)} - {int(away_goals)}"


def poisson_probability(goals: int, expected_goals: float) -> float:
    if expected_goals < 0:
        raise ValueError("expected_goals must be non-negative")
    return math.exp(-expected_goals) * (expected_goals ** goals) / math.factorial(goals)


def probability_to_decimal_odds(probability: float | None) -> float | None:
    if probability is None or probability <= 0:
        return None
    return round(1.0 / probability, 3)


def fair_decimal_odds(probability: float | None) -> float | None:
    return probability_to_decimal_odds(probability)


def probability_to_american_odds(probability: float | None) -> str:
    if probability is None or probability <= 0 or probability >= 1:
        return ""
    if probability >= 0.5:
        return str(int(round(-100 * probability / (1 - probability))))
    return f"+{int(round(100 * (1 - probability) / probability))}"


def implied_percentage(probability: float | None) -> float | None:
    if probability is None:
        return None
    return round(probability * 100.0, 2)


def _score_matrix(home_xg: float, away_xg: float, max_goals: int) -> pd.DataFrame:
    rows = []
    for home_goals in range(max_goals + 1):
        home_prob = poisson_probability(home_goals, home_xg)
        for away_goals in range(max_goals + 1):
            probability = home_prob * poisson_probability(away_goals, away_xg)
            rows.append({
                "home_goals": home_goals,
                "away_goals": away_goals,
                "probability": probability,
                "fair_odds": fair_decimal_odds(probability),
                "correct_score_american_odds": probability_to_american_odds(probability),
                "implied_percentage": implied_percentage(probability),
                "score_label": excel_safe_score_label(home_goals, away_goals),
            })
    frame = pd.DataFrame(rows)
    mass = frame["probability"].sum()
    if mass > 0:
        frame["probability"] = frame["probability"] / mass
        frame["fair_odds"] = frame["probability"].apply(fair_decimal_odds)
        frame["correct_score_american_odds"] = frame["probability"].apply(probability_to_american_odds)
        frame["implied_percentage"] = frame["probability"].apply(implied_percentage)
    return frame


def build_poisson_board_for_match(
    *,
    home_team: str,
    away_team: str,
    projected_home_xg: float,
    projected_away_xg: float,
    max_goals: int = 6,
    metadata: dict[str, Any] | None = None,
) -> dict[str, pd.DataFrame]:
    matrix = _score_matrix(projected_home_xg, projected_away_xg, max_goals)
    home_win = float(matrix[matrix["home_goals"] > matrix["away_goals"]]["probability"].sum())
    draw = float(matrix[matrix["home_goals"] == matrix["away_goals"]]["probability"].sum())
    away_win = float(matrix[matrix["home_goals"] < matrix["away_goals"]]["probability"].sum())

    one_x_two = pd.DataFrame([{
        "home_team": home_team,
        "away_team": away_team,
        "home_win_probability": home_win,
        "draw_probability": draw,
        "away_win_probability": away_win,
        "home_implied_percentage": implied_percentage(home_win),
        "draw_implied_percentage": implied_percentage(draw),
        "away_implied_percentage": implied_percentage(away_win),
        "home_fair_odds": fair_decimal_odds(home_win),
        "draw_fair_odds": fair_decimal_odds(draw),
        "away_fair_odds": fair_decimal_odds(away_win),
        "home_american_odds": probability_to_american_odds(home_win),
        "draw_american_odds": probability_to_american_odds(draw),
        "away_american_odds": probability_to_american_odds(away_win),
    }])

    totals_rows = []
    for line in TOTAL_LINES:
        over = float(matrix[matrix["home_goals"] + matrix["away_goals"] > line]["probability"].sum())
        under = 1.0 - over
        totals_rows.append({
            "home_team": home_team,
            "away_team": away_team,
            "line": line,
            "over_probability": over,
            "under_probability": under,
            "over_implied_percentage": implied_percentage(over),
            "under_implied_percentage": implied_percentage(under),
            "over_fair_odds": fair_decimal_odds(over),
            "under_fair_odds": fair_decimal_odds(under),
            "over_american_odds": probability_to_american_odds(over),
            "under_american_odds": probability_to_american_odds(under),
        })
    totals = pd.DataFrame(totals_rows)

    btts_yes = float(matrix[(matrix["home_goals"] > 0) & (matrix["away_goals"] > 0)]["probability"].sum())
    btts_no = 1.0 - btts_yes
    btts = pd.DataFrame([{
        "home_team": home_team,
        "away_team": away_team,
        "yes_probability": btts_yes,
        "no_probability": btts_no,
        "yes_implied_percentage": implied_percentage(btts_yes),
        "no_implied_percentage": implied_percentage(btts_no),
        "yes_fair_odds": fair_decimal_odds(btts_yes),
        "no_fair_odds": fair_decimal_odds(btts_no),
        "btts_yes_american_odds": probability_to_american_odds(btts_yes),
        "btts_no_american_odds": probability_to_american_odds(btts_no),
    }])

    home_clean = float(matrix[matrix["away_goals"] == 0]["probability"].sum())
    away_clean = float(matrix[matrix["home_goals"] == 0]["probability"].sum())
    clean_sheets = pd.DataFrame([{
        "home_team": home_team,
        "away_team": away_team,
        "home_clean_sheet_probability": home_clean,
        "away_clean_sheet_probability": away_clean,
        "home_concedes_probability": 1.0 - home_clean,
        "away_concedes_probability": 1.0 - away_clean,
        "home_clean_sheet_fair_odds": fair_decimal_odds(home_clean),
        "away_clean_sheet_fair_odds": fair_decimal_odds(away_clean),
        "home_clean_sheet_american_odds": probability_to_american_odds(home_clean),
        "away_clean_sheet_american_odds": probability_to_american_odds(away_clean),
        "home_concedes_american_odds": probability_to_american_odds(1.0 - home_clean),
        "away_concedes_american_odds": probability_to_american_odds(1.0 - away_clean),
    }])

    matrix = matrix.copy()
    matrix.insert(0, "away_team", away_team)
    matrix.insert(0, "home_team", home_team)
    likely = matrix.sort_values("probability", ascending=False).iloc[0]
    over_2_5 = float(totals.loc[totals["line"] == 2.5, "over_probability"].iloc[0])
    under_2_5 = float(totals.loc[totals["line"] == 2.5, "under_probability"].iloc[0])
    meta = metadata or {}
    match_summary = pd.DataFrame([{
        "home_team": home_team,
        "away_team": away_team,
        "projected_home_xg": projected_home_xg,
        "projected_away_xg": projected_away_xg,
        "projected_total": projected_home_xg + projected_away_xg,
        "most_likely_score": likely["score_label"],
        "most_likely_score_probability": float(likely["probability"]),
        "most_likely_score_american_odds": likely["correct_score_american_odds"],
        "home_win_probability": home_win,
        "draw_probability": draw,
        "away_win_probability": away_win,
        "home_win_american_odds": probability_to_american_odds(home_win),
        "draw_american_odds": probability_to_american_odds(draw),
        "away_win_american_odds": probability_to_american_odds(away_win),
        "over_2_5_probability": over_2_5,
        "under_2_5_probability": under_2_5,
        "over_2_5_american_odds": probability_to_american_odds(over_2_5),
        "under_2_5_american_odds": probability_to_american_odds(under_2_5),
        "btts_yes_probability": btts_yes,
        "btts_no_probability": btts_no,
        "btts_yes_american_odds": probability_to_american_odds(btts_yes),
        "btts_no_american_odds": probability_to_american_odds(btts_no),
        "home_clean_sheet_probability": home_clean,
        "away_clean_sheet_probability": away_clean,
        "data_support_level": meta.get("data_support_level", ""),
        "confidence_label": meta.get("confidence_label", ""),
        "style_inputs_available": meta.get("style_inputs_available", False),
        "is_sample_data": meta.get("is_sample_data", False),
        "source_tier": meta.get("source_tier", ""),
        "rating_status": meta.get("rating_status", ""),
        "primary_warning": meta.get("primary_warning", ""),
        "source_warning": meta.get("source_warning", ""),
        "rating_warning": meta.get("rating_warning", ""),
        "style_warning": meta.get("style_warning", ""),
        "guardrail_flags": meta.get("guardrail_flags", ""),
    }])
    return {
        "one_x_two": one_x_two,
        "totals": totals,
        "btts": btts,
        "clean_sheets": clean_sheets,
        "correct_score_matrix": matrix,
        "match_summary": match_summary,
    }


def build_poisson_boards(rows: pd.DataFrame, max_goals: int = 6) -> dict[str, pd.DataFrame]:
    tables = {
        "one_x_two": [],
        "totals": [],
        "btts": [],
        "clean_sheets": [],
        "correct_score_matrix": [],
        "match_summary": [],
    }
    for _, row in rows.iterrows():
        home_xg = row.get("projected_home_xg")
        away_xg = row.get("projected_away_xg")
        if pd.isna(home_xg) or pd.isna(away_xg):
            continue
        if float(home_xg) < 0 or float(away_xg) < 0:
            continue
        board = build_poisson_board_for_match(
            home_team=str(row.get("team_a", "")),
            away_team=str(row.get("team_b", "")),
            projected_home_xg=float(home_xg),
            projected_away_xg=float(away_xg),
            max_goals=max_goals,
            metadata={
                "data_support_level": row.get("data_support_level", ""),
                "confidence_label": row.get("confidence_label", ""),
                "style_inputs_available": row.get("style_inputs_available", False),
                "is_sample_data": row.get("is_sample_data", False),
                "source_tier": row.get("source_tier", ""),
                "rating_status": row.get("rating_status", ""),
                "primary_warning": row.get("primary_warning", ""),
                "source_warning": row.get("source_warning", ""),
                "rating_warning": row.get("rating_warning", ""),
                "style_warning": row.get("style_warning", ""),
                "guardrail_flags": row.get("guardrail_flags", ""),
                "warnings": row.get("warnings_text", ""),
            },
        )
        for name, frame in board.items():
            tables[name].append(frame)
    return {
        name: pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        for name, frames in tables.items()
    }


def write_poisson_outputs(rows: pd.DataFrame, output_dir: str | Path, max_goals: int = 6) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    tables = build_poisson_boards(rows, max_goals=max_goals)
    paths = {
        "one_x_two": output / "poisson_1x2.csv",
        "totals": output / "poisson_totals.csv",
        "btts": output / "poisson_btts.csv",
        "clean_sheets": output / "poisson_clean_sheets.csv",
        "correct_score_matrix": output / "poisson_correct_score_matrix.csv",
        "match_summary": output / "poisson_match_summary.csv",
    }
    for name, path in paths.items():
        tables[name].to_csv(path, index=False)
    summary_path = output / "poisson_summary.md"
    summary_path.write_text(build_poisson_summary_markdown(tables), encoding="utf-8")
    return {"tables": tables, "paths": {**{k: str(v) for k, v in paths.items()}, "summary": str(summary_path)}}


def build_poisson_summary_markdown(tables: dict[str, pd.DataFrame]) -> str:
    summary = tables.get("match_summary", pd.DataFrame())
    if summary.empty:
        return "\n".join([
            "# Poisson Probability Board",
            "",
            "No valid projected xG rows were available, so no Poisson board was generated.",
            "",
        ])
    top_home = summary.sort_values("home_win_probability", ascending=False).iloc[0]
    top_away = summary.sort_values("away_win_probability", ascending=False).iloc[0]
    top_over = summary.sort_values("over_2_5_probability", ascending=False).iloc[0]
    common_score = summary["most_likely_score"].mode().iloc[0]
    lines = [
        "# Poisson Probability Board",
        "",
        "Poisson turns projected team xG into result, totals, BTTS, clean sheet, and correct-score probabilities.",
        "These are probability outputs and model-implied American odds, not recommendations.",
        "",
        "## Highlights",
        "",
        f"- Matches: `{len(summary)}`",
        f"- Highest home win probability: `{top_home['home_team']} vs {top_home['away_team']}` `{top_home['home_win_probability']:.3f}` `{top_home['home_win_american_odds']}`",
        f"- Highest away win probability: `{top_away['home_team']} vs {top_away['away_team']}` `{top_away['away_win_probability']:.3f}` `{top_away['away_win_american_odds']}`",
        f"- Highest over 2.5 probability: `{top_over['home_team']} vs {top_over['away_team']}` `{top_over['over_2_5_probability']:.3f}` `{top_over['over_2_5_american_odds']}`",
        f"- Most common correct score: `{common_score}`",
        "",
        "## Match Summary",
        "",
        "| match | xG | 1/X/2 | 1/X/2 fair American odds | O2.5/U2.5 | O2.5/U2.5 fair American odds | BTTS Y/N | BTTS Y/N fair American odds | likely score | likely score fair American odds | support | short warning |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['home_team']} vs {row['away_team']} | "
            f"{float(row['projected_home_xg']):.3f} / {float(row['projected_away_xg']):.3f} | "
            f"{float(row['home_win_probability']) * 100:.1f}% / {float(row['draw_probability']) * 100:.1f}% / {float(row['away_win_probability']) * 100:.1f}% | "
            f"{row['home_win_american_odds']} / {row['draw_american_odds']} / {row['away_win_american_odds']} | "
            f"{float(row['over_2_5_probability']) * 100:.1f}% / {float(row['under_2_5_probability']) * 100:.1f}% | "
            f"{row['over_2_5_american_odds']} / {row['under_2_5_american_odds']} | "
            f"{float(row['btts_yes_probability']) * 100:.1f}% / {float(row['btts_no_probability']) * 100:.1f}% | "
            f"{row['btts_yes_american_odds']} / {row['btts_no_american_odds']} | "
            f"{row['most_likely_score']} | {row['most_likely_score_american_odds']} | "
            f"{row.get('data_support_level', '')} | {row.get('primary_warning') or row.get('rating_warning') or row.get('style_warning') or ''} |"
        )
    lines.append("")
    return "\n".join(lines)
