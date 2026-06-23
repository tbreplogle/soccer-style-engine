from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from evidence import STYLE_TO_METRICS, metric_evidence, notes_for_team, recent_shift
from style_features import STYLE_COLUMNS, style_rankings


IDENTITY_PLAYBOOK = {
    "Defensive Low Block": {
        "summary": "comfortable without the ball, protects dangerous areas, and tries to keep the game compact",
        "strengths": "can mute high-tempo opponents, shrink central space, and keep totals lower if concentration holds",
        "watchouts": "can get pinned deep, struggle to escape pressure, and concede if the block is stretched wide or forced to chase",
        "best": "reckless vertical teams that need space behind the line",
        "worst": "patient possession teams with wide switches and elite box occupation",
    },
    "Fast / Vertical Run Threat": {
        "summary": "plays forward quickly, creates runs behind, and wants the game to open up",
        "strengths": "dangerous in transition, can punish high lines, and can create chances without long possession spells",
        "watchouts": "can become impatient against compact blocks and may give the ball away in bad spots",
        "best": "high-line or possession teams that leave transition lanes",
        "worst": "disciplined low blocks that deny space behind and force slower buildup",
    },
    "Possession + High Press": {
        "summary": "controls the ball and tries to win it back high when possession is lost",
        "strengths": "can suffocate weaker buildout teams and turn possession into territory",
        "watchouts": "can be exposed behind the press if the first wave gets broken",
        "best": "teams with weak buildup or sloppy midfield turnovers",
        "worst": "vertical teams with clean outlets behind the press",
    },
    "Possession Controller": {
        "summary": "values the ball, slows the game, and tries to create control through repeated possessions",
        "strengths": "can reduce opponent attacks and force long defensive spells",
        "watchouts": "can create sterile possession if progression and box entries are weak",
        "best": "teams that cannot press or cannot hold territory",
        "worst": "compact blocks that let them pass harmlessly outside the danger zones",
    },
    "Aggressive Pressing": {
        "summary": "defends forward, creates pressure events, and wants turnovers before the opponent settles",
        "strengths": "can generate short-field chances and disrupt possession teams",
        "watchouts": "can leave space if the press is bypassed",
        "best": "slow buildup teams with shaky ball security",
        "worst": "teams with direct outlets and runners behind the press",
    },
    "Fast / Vertical": {
        "summary": "leans direct and wants quicker attacks rather than long possession control",
        "strengths": "can change game state quickly and punish slow defensive recovery",
        "watchouts": "may lack control if the game becomes settled possession",
        "best": "teams that leave space between lines",
        "worst": "deep compact defensive teams",
    },
    "Off-Ball Runner": {
        "summary": "creates value through movement, sprints, and runs behind/around the line",
        "strengths": "can stretch compact teams and create blind-side danger",
        "watchouts": "needs service; movement is wasted if progression is poor",
        "best": "static back lines and teams that track runners poorly",
        "worst": "compact teams with disciplined runner tracking",
    },
    "Wide Field Stretcher": {
        "summary": "uses width and lateral spacing to stretch the opponent",
        "strengths": "can open crossing lanes, switches, and back-post chances",
        "watchouts": "can become predictable if central threat is missing",
        "best": "narrow defensive teams",
        "worst": "teams that defend wide areas well and dominate aerially",
    },
    "Balanced / Mixed": {
        "summary": "does not show a dominant style signal yet in the tracked data",
        "strengths": "can adapt if the underlying talent supports multiple approaches",
        "watchouts": "may be noisy data or a team with no consistent identity yet",
        "best": "unclear until more matches are tracked",
        "worst": "unclear until more matches are tracked",
    },
}


IDENTITY_TO_STYLE_METRICS = {
    "Defensive Low Block": ["avg_block_height", "possession_pct", "opponent_box_touches_allowed", "xga_per90", "ppda"],
    "Fast / Vertical Run Threat": ["direct_speed_mps", "fast_attacks_per90", "runs_in_behind_per90", "sprints_per90", "progressive_passes_per90"],
    "Possession + High Press": ["possession_pct", "field_tilt_pct", "avg_possession_seconds", "passes_per_possession", "ppda", "high_regains_per90", "avg_block_height"],
    "Possession Controller": ["possession_pct", "field_tilt_pct", "avg_possession_seconds", "passes_per_possession", "central_progression_pct"],
    "Aggressive Pressing": ["ppda", "high_regains_per90", "avg_block_height", "touch_x_mean"],
    "Fast / Vertical": ["direct_speed_mps", "fast_attacks_per90", "progressive_passes_per90", "progressive_carries_per90"],
    "Off-Ball Runner": ["runs_in_behind_per90", "sprints_per90", "fast_attacks_per90"],
    "Wide Field Stretcher": ["avg_team_width", "touch_y_spread", "avg_team_depth"],
    "Balanced / Mixed": ["possession_pct", "field_tilt_pct", "direct_speed_mps", "avg_block_height"],
}


def _top_styles(summary: pd.DataFrame, team: str, n: int = 3) -> str:
    rankings = style_rankings(summary, team)[:n]
    return "; ".join(f"{name.replace('_rating', '').replace('_', ' ')}={score:.1f}" for name, score in rankings)


def build_team_identity_reports(summary: pd.DataFrame, match_log: pd.DataFrame, notes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Create scout-like team identity reports from measured style data.

    This is called an agent because it interprets evidence, but v1 is deliberately
    deterministic and auditable. It should not make a betting pick.
    """
    notes = notes if notes is not None else pd.DataFrame()
    reports = []
    for _, row in summary.iterrows():
        team = row["team"]
        identity = row["primary_identity"]
        playbook = IDENTITY_PLAYBOOK.get(identity, IDENTITY_PLAYBOOK["Balanced / Mixed"])
        metrics = IDENTITY_TO_STYLE_METRICS.get(identity, [])
        evidence = metric_evidence(match_log, team, metrics, max_items=6)
        human_notes = notes_for_team(notes, team)

        reports.append({
            "team": team,
            "primary_identity": identity,
            "identity_confidence": int(row["identity_confidence"]),
            "top_style_scores": _top_styles(summary, team),
            "identity_summary": f"{team} profiles as {identity}: {playbook['summary']}.",
            "measured_evidence": " | ".join(evidence),
            "human_scouting_notes": " | ".join(human_notes) if human_notes else "None yet",
            "strengths": playbook["strengths"],
            "watchouts": playbook["watchouts"],
            "best_matchup_type": playbook["best"],
            "worst_matchup_type": playbook["worst"],
            "recent_shift": recent_shift(match_log, team),
            "guardrail_status": guardrail_status(row, evidence, human_notes),
        })
    return pd.DataFrame(reports).sort_values("team").reset_index(drop=True)


def guardrail_status(row: pd.Series, evidence: list[str], human_notes: list[str]) -> str:
    if int(row.get("matches_tracked", 0)) < 3:
        return "EARLY_SAMPLE: do not over-trust identity yet"
    if not evidence:
        return "NEEDS_REVIEW: no metric evidence attached"
    if human_notes and int(row["identity_confidence"]) < 55:
        return "CHECK_HUMAN_NOTE: note exists but measured identity is weak"
    return "SUPPORTED_BY_TRACKED_STYLE"


def reports_to_markdown(reports: pd.DataFrame) -> str:
    lines = ["# Team Identity Agent Report", "", "This report describes how teams play. It is not a betting sheet.", ""]
    for _, r in reports.iterrows():
        lines.extend([
            f"## {r['team']}",
            f"**Identity:** {r['primary_identity']} ({r['identity_confidence']}/100 style confidence)",
            "",
            r["identity_summary"],
            "",
            f"**Top style scores:** {r['top_style_scores']}",
            "",
            f"**Measured evidence:** {r['measured_evidence']}",
            "",
            f"**Human notes:** {r['human_scouting_notes']}",
            "",
            f"**Strengths:** {r['strengths']}",
            "",
            f"**Watchouts:** {r['watchouts']}",
            "",
            f"**Best matchup type:** {r['best_matchup_type']}",
            "",
            f"**Worst matchup type:** {r['worst_matchup_type']}",
            "",
            f"**Recent shift:** {r['recent_shift']}",
            "",
            f"**Guardrail:** {r['guardrail_status']}",
            "",
        ])
    return "\n".join(lines)
