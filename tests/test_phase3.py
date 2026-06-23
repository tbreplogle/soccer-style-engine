from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evidence import load_scouting_notes
from matchup_agent import build_matchup_agent_reports
from style_features import summarize_team_style
from team_identity_agent import build_team_identity_reports


def _load_inputs():
    match_log = pd.read_csv(ROOT / "data" / "sample_team_match_style_log.csv")
    matchups = pd.read_csv(ROOT / "data" / "sample_matchups.csv")
    notes = load_scouting_notes(str(ROOT / "data" / "sample_scouting_notes.csv"))
    return match_log, matchups, notes


def test_style_summary_classifies_core_archetypes():
    match_log, _, _ = _load_inputs()
    summary = summarize_team_style(match_log)
    identities = summary.set_index("team")["primary_identity"].to_dict()

    assert identities["Morocco"] == "Defensive Low Block"
    assert identities["Brazil"] == "Fast / Vertical Run Threat"


def test_team_identity_agent_includes_evidence_and_human_notes():
    match_log, _, notes = _load_inputs()
    summary = summarize_team_style(match_log)
    reports = build_team_identity_reports(summary, match_log, notes)
    morocco = reports.set_index("team").loc["Morocco"]

    assert morocco["measured_evidence"] != ""
    assert "Human" not in morocco["measured_evidence"]
    assert "Comfortable giving up possession" in morocco["human_scouting_notes"]
    assert morocco["guardrail_status"] in {
        "SUPPORTED_BY_TRACKED_STYLE",
        "EARLY_SAMPLE: do not over-trust identity yet",
        "CHECK_HUMAN_NOTE: note exists but measured identity is weak",
    }


def test_matchup_agent_refuses_to_make_betting_projection():
    match_log, matchups, notes = _load_inputs()
    summary = summarize_team_style(match_log)
    reports = build_team_identity_reports(summary, match_log, notes)
    matchup_reports = build_matchup_agent_reports(summary, reports, matchups)

    assert not matchup_reports.empty
    assert matchup_reports["prediction_status"].eq("STYLE READ ONLY - no betting projection until backtest layer exists").all()
