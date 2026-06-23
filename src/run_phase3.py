from __future__ import annotations

from pathlib import Path
import pandas as pd

from evidence import load_scouting_notes
from matchup_agent import build_matchup_agent_reports, matchup_reports_to_markdown
from style_features import summarize_team_style
from team_identity_agent import build_team_identity_reports, reports_to_markdown

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    match_log = pd.read_csv(DATA / "sample_team_match_style_log.csv")
    matchups = pd.read_csv(DATA / "sample_matchups.csv")
    notes = load_scouting_notes(str(DATA / "sample_scouting_notes.csv"))

    summary = summarize_team_style(match_log)
    team_reports = build_team_identity_reports(summary, match_log, notes)
    matchup_reports = build_matchup_agent_reports(summary, team_reports, matchups)

    summary.to_csv(OUT / "team_style_summary.csv", index=False)
    team_reports.to_csv(OUT / "team_identity_agent_report.csv", index=False)
    matchup_reports.to_csv(OUT / "matchup_agent_report.csv", index=False)
    (OUT / "team_identity_agent_report.md").write_text(reports_to_markdown(team_reports), encoding="utf-8")
    (OUT / "matchup_agent_report.md").write_text(matchup_reports_to_markdown(matchup_reports), encoding="utf-8")

    print("Wrote outputs:")
    for name in [
        "team_style_summary.csv",
        "team_identity_agent_report.csv",
        "team_identity_agent_report.md",
        "matchup_agent_report.csv",
        "matchup_agent_report.md",
    ]:
        print(f"- {OUT / name}")

    print("\nTeam Identity Agent preview:")
    print(team_reports[["team", "primary_identity", "identity_confidence", "guardrail_status"]].to_string(index=False))
    print("\nMatchup Agent preview:")
    print(matchup_reports[["matchup_id", "team_a", "team_b", "tempo_read"]].to_string(index=False))


if __name__ == "__main__":
    main()
