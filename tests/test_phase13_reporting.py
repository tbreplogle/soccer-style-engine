from __future__ import annotations

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.data_ingestion.football_data_current import normalize_current_inputs
from src.reports.projection_report import compare_club_projection_profiles, compare_international_projection_profiles, disagreement_flags
from src.reports.slate_report import build_club_slate_report, build_international_slate_report


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FOLDER = ROOT / "data" / "sample" / "football-data"


def _current_csv(tmp_path: Path) -> Path:
    path = tmp_path / "current.csv"
    normalize_current_inputs(SAMPLE_FOLDER, output_path=path, league="SYN", season="2025-2026")
    return path


def _international_csv(tmp_path: Path) -> Path:
    rows = []
    teams = ["Brazil", "Morocco", "France", "Argentina"]
    for i in range(12):
        rows.append({
            "match_id": f"intl_{i}",
            "date": f"2022-11-{10+i:02d}",
            "competition_id": 43,
            "competition_name": "FIFA World Cup",
            "season_id": 106,
            "season_name": "2022",
            "home_team": teams[i % 4],
            "away_team": teams[(i + 1) % 4],
            "home_score": i % 3,
            "away_score": (i + 1) % 2,
            "neutral_site": "true",
            "match_stage": "Group Stage",
            "tournament_round": "Group Stage",
            "country_or_team_type": "national_team",
            "data_source": "synthetic",
            "has_event_data": False,
            "has_360_data": False,
            "data_mode": "historical_match_results",
            "event_style_flags": "missing_event_data",
        })
    path = tmp_path / "international.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_club_slate_report_generation(tmp_path):
    current = _current_csv(tmp_path)
    result = build_club_slate_report(current, "2026-02-20", league="SYN", output_dir=tmp_path, projection_output_dir=tmp_path, slate_type="historical", max_matches=2)
    assert not result["results"].empty
    assert result["markdown_path"].exists()
    assert result["csv_path"].exists()
    assert result["results"]["betting_recommendation"].isna().all()


def test_international_slate_report_generation(tmp_path):
    intl = _international_csv(tmp_path)
    result = build_international_slate_report(intl, "2022-11-22", team_a="Brazil", team_b="Morocco", neutral_site="true", output_dir=tmp_path, projection_output_dir=tmp_path)
    assert not result["results"].empty
    assert result["markdown_path"].exists()
    assert result["csv_path"].exists()
    assert result["results"]["betting_recommendation"].isna().all()


def test_profile_comparison_includes_profiles_and_outputs(tmp_path):
    current = _current_csv(tmp_path)
    profiles = ["score_projection", "model_only"]
    result = compare_club_projection_profiles(current, "Red FC", "Blue FC", "2026-02-01", profiles=profiles, output_dir=tmp_path, projection_output_dir=tmp_path, league="SYN")
    assert set(result["results"]["projection_profile"]) == set(profiles)
    assert result["markdown_path"].exists()
    assert result["csv_path"].exists()


def test_international_profile_comparison_includes_profiles(tmp_path):
    intl = _international_csv(tmp_path)
    profiles = ["international_score_projection", "international_model_only"]
    result = compare_international_projection_profiles(intl, "Brazil", "Morocco", "2022-11-22", neutral_site="true", profiles=profiles, output_dir=tmp_path, projection_output_dir=tmp_path)
    assert set(result["results"]["projection_profile"]) == set(profiles)


def test_disagreement_flags_trigger():
    frame = pd.DataFrame({
        "home_win_prob": [0.2, 0.5],
        "projected_total": [1.8, 2.4],
        "confidence_score": [45, 80],
        "home_xg_final": [1.0, 1.2],
        "away_xg_final": [0.8, 1.2],
        "model_market_gap_summary": ["Largest model-market probability gap: home +0.150", ""],
    })
    flags = disagreement_flags(frame)
    assert "high_winner_disagreement" in flags
    assert "high_total_disagreement" in flags
    assert "high_confidence_disagreement" in flags
    assert "market_vs_model_disagreement" in flags


def test_manual_matchup_csvs_are_parsed(tmp_path):
    current = _current_csv(tmp_path)
    club = build_club_slate_report(current, "2026-02-01", matchups_csv=ROOT / "data" / "sample" / "manual_club_matchups.csv", output_dir=tmp_path / "club", projection_output_dir=tmp_path / "club")
    intl = build_international_slate_report(_international_csv(tmp_path), "2022-11-22", matchups_csv=ROOT / "data" / "sample" / "manual_international_matchups.csv", output_dir=tmp_path / "intl", projection_output_dir=tmp_path / "intl")
    assert club["slate_type"] == "manual_matchup_slate"
    assert intl["slate_type"] == "manual_matchup_slate"


def test_generated_outputs_stay_in_ignored_folders():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "outputs/projections/*" in gitignore
    assert "outputs/reports/*" in gitignore


def test_phase13_cli_smoke(tmp_path):
    current = _current_csv(tmp_path)
    intl = _international_csv(tmp_path)
    cmds = [
        [sys.executable, "-m", "src.cli", "build-club-slate", "--input", str(current), "--as-of-date", "2026-02-20", "--league", "SYN", "--slate-type", "historical", "--max-matches", "1", "--output-dir", str(tmp_path / "reports"), "--projection-output-dir", str(tmp_path / "proj")],
        [sys.executable, "-m", "src.cli", "compare-club-profiles", "--input", str(current), "--home", "Red FC", "--away", "Blue FC", "--as-of-date", "2026-02-01", "--profiles", "score_projection,model_only", "--output-dir", str(tmp_path / "reports"), "--projection-output-dir", str(tmp_path / "proj")],
        [sys.executable, "-m", "src.cli", "build-international-slate", "--input", str(intl), "--as-of-date", "2022-11-22", "--team-a", "Brazil", "--team-b", "Morocco", "--neutral-site", "true", "--output-dir", str(tmp_path / "reports"), "--projection-output-dir", str(tmp_path / "proj")],
        [sys.executable, "-m", "src.cli", "compare-international-profiles", "--input", str(intl), "--team-a", "Brazil", "--team-b", "Morocco", "--as-of-date", "2022-11-22", "--neutral-site", "true", "--profiles", "international_score_projection,international_model_only", "--output-dir", str(tmp_path / "reports"), "--projection-output-dir", str(tmp_path / "proj")],
    ]
    for cmd in cmds:
        completed = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
        assert completed.returncode == 0
    written = list((tmp_path / "proj").glob("*.csv"))
    assert written


def test_historical_slate_uses_historical_validation_type(tmp_path):
    result = build_club_slate_report(_current_csv(tmp_path), "2026-02-20", league="SYN", output_dir=tmp_path, projection_output_dir=tmp_path, slate_type="historical", max_matches=1)
    assert result["slate_type"] == "historical_validation_slate"
