from __future__ import annotations

import pandas as pd


STYLE_COLUMNS = [
    "control_rating",
    "verticality_rating",
    "low_block_rating",
    "pressing_rating",
    "movement_width_rating",
    "off_ball_run_rating",
    "territory_rating",
    "defensive_resistance_rating",
    "tempo_rating",
]


def build_matchup_agent_reports(summary: pd.DataFrame, team_reports: pd.DataFrame, matchups: pd.DataFrame) -> pd.DataFrame:
    lookup = summary.set_index("team")
    report_lookup = team_reports.set_index("team")
    rows = []
    for _, m in matchups.iterrows():
        a, b = m["team_a"], m["team_b"]
        if a not in lookup.index or b not in lookup.index:
            continue
        ar, br = lookup.loc[a], lookup.loc[b]
        rows.append({
            "matchup_id": m["matchup_id"],
            "team_a": a,
            "team_b": b,
            "team_a_identity": ar["primary_identity"],
            "team_b_identity": br["primary_identity"],
            "style_clash": explain_style_clash(a, b, ar, br),
            "likely_game_state": likely_game_state(a, b, ar, br),
            "tempo_read": tempo_read(a, b, ar, br),
            "prediction_status": "STYLE READ ONLY - no betting projection until backtest layer exists",
            "team_a_guardrail": report_lookup.loc[a, "guardrail_status"] if a in report_lookup.index else "missing report",
            "team_b_guardrail": report_lookup.loc[b, "guardrail_status"] if b in report_lookup.index else "missing report",
        })
    return pd.DataFrame(rows)


def explain_style_clash(a: str, b: str, ar: pd.Series, br: pd.Series) -> str:
    notes = []
    if ar["verticality_rating"] >= 70 and br["low_block_rating"] >= 70:
        notes.append(f"{a}'s vertical pace is meeting {b}'s compact low-block identity")
    if br["verticality_rating"] >= 70 and ar["low_block_rating"] >= 70:
        notes.append(f"{b}'s vertical pace is meeting {a}'s compact low-block identity")
    if ar["control_rating"] - br["pressing_rating"] >= 15:
        notes.append(f"{a} has a cleaner possession path because {b}'s pressure profile is not strong enough to disrupt it")
    if br["control_rating"] - ar["pressing_rating"] >= 15:
        notes.append(f"{b} has a cleaner possession path because {a}'s pressure profile is not strong enough to disrupt it")
    if ar["pressing_rating"] - br["control_rating"] >= 15:
        notes.append(f"{a}'s press can make {b}'s buildup uncomfortable")
    if br["pressing_rating"] - ar["control_rating"] >= 15:
        notes.append(f"{b}'s press can make {a}'s buildup uncomfortable")
    if ar["movement_width_rating"] >= 70 and br["low_block_rating"] >= 70:
        notes.append(f"{a}'s width matters because it can stretch {b}'s low block")
    if br["movement_width_rating"] >= 70 and ar["low_block_rating"] >= 70:
        notes.append(f"{b}'s width matters because it can stretch {a}'s low block")
    return "; ".join(notes) if notes else "No dominant style clash yet; needs more tracked matches or a tighter matchup signal"


def likely_game_state(a: str, b: str, ar: pd.Series, br: pd.Series) -> str:
    control_edge = ar["control_rating"] - br["control_rating"]
    territory_edge = ar["territory_rating"] - br["territory_rating"]
    if control_edge >= 12 and territory_edge >= 10:
        return f"{a} likely owns more of the ball and territory; {b} may be defending longer spells."
    if control_edge <= -12 and territory_edge <= -10:
        return f"{b} likely owns more of the ball and territory; {a} may be defending longer spells."
    if ar["low_block_rating"] >= 70 and br["verticality_rating"] >= 70:
        return f"{a} may allow possession and try to keep {b}'s speed in front of the block."
    if br["low_block_rating"] >= 70 and ar["verticality_rating"] >= 70:
        return f"{b} may allow possession and try to keep {a}'s speed in front of the block."
    return "Game state is not obvious from style alone; avoid forcing a story."


def tempo_read(a: str, b: str, ar: pd.Series, br: pd.Series) -> str:
    avg_tempo = (float(ar["tempo_rating"]) + float(br["tempo_rating"])) / 2
    low_block_drag = max(float(ar["low_block_rating"]), float(br["low_block_rating"]))
    if avg_tempo >= 72 and low_block_drag < 70:
        return "Higher-tempo shape: both profiles allow pace/transition to show up."
    if low_block_drag >= 75 and avg_tempo < 72:
        return "Tempo may get dragged down by compact defensive posture."
    if avg_tempo >= 70 and low_block_drag >= 70:
        return "Split signal: one side wants speed, the other may try to compress the game."
    return "Neutral tempo read."


def matchup_reports_to_markdown(reports: pd.DataFrame) -> str:
    lines = ["# Matchup Intelligence Agent Report", "", "This compares style identities. It does not make picks yet.", ""]
    for _, r in reports.iterrows():
        lines.extend([
            f"## {r['team_a']} vs {r['team_b']}",
            f"**Identities:** {r['team_a']} = {r['team_a_identity']} | {r['team_b']} = {r['team_b_identity']}",
            "",
            f"**Style clash:** {r['style_clash']}",
            "",
            f"**Likely game state:** {r['likely_game_state']}",
            "",
            f"**Tempo read:** {r['tempo_read']}",
            "",
            f"**Status:** {r['prediction_status']}",
            "",
        ])
    return "\n".join(lines)
