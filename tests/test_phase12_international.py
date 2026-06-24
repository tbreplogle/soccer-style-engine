from __future__ import annotations

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.data_ingestion.international_data import build_international_match_dataset, list_international_competitions
from src.models.international_backtest import run_international_backtest
from src.models.international_context import international_home_advantage
from src.models.international_projection import project_international_match, score_international_confidence
from src.models.international_ratings import build_international_team_ratings


ROOT = Path(__file__).resolve().parents[1]


def _synthetic_statsbomb(root: Path) -> Path:
    (root / "matches" / "43").mkdir(parents=True)
    (root / "events").mkdir()
    (root / "competitions.json").write_text(json.dumps([
        {"competition_id": 43, "season_id": 106, "competition_name": "FIFA World Cup", "season_name": "2022"},
        {"competition_id": 2, "season_id": 1, "competition_name": "Premier League", "season_name": "2022"},
    ]), encoding="utf-8")
    matches = []
    teams = ["Brazil", "Morocco", "France", "Argentina"]
    for i in range(12):
        home = teams[i % 4]
        away = teams[(i + 1) % 4]
        matches.append({
            "match_id": 1000 + i,
            "match_date": f"2022-11-{10 + i:02d}",
            "home_team": {"home_team_name": home},
            "away_team": {"away_team_name": away},
            "home_score": i % 3,
            "away_score": (i + 1) % 2,
            "competition_stage": {"name": "Group Stage"},
            "neutral_site": True,
        })
        if i == 0:
            (root / "events" / f"{1000 + i}.json").write_text(json.dumps([
                {"type": {"name": "Shot"}, "team": {"name": home}, "shot": {"statsbomb_xg": 0.2, "outcome": {"name": "Saved"}}, "location": [90, 40]},
                {"type": {"name": "Pressure"}, "team": {"name": away}, "location": [70, 30]},
            ]), encoding="utf-8")
    (root / "matches" / "43" / "106.json").write_text(json.dumps(matches), encoding="utf-8")
    return root


def test_international_competition_detection(tmp_path):
    root = _synthetic_statsbomb(tmp_path / "statsbomb")
    comps = list_international_competitions(root)
    assert comps["competition_name"].tolist() == ["FIFA World Cup"]


def test_builder_handles_missing_statsbomb_gracefully(tmp_path):
    result = build_international_match_dataset(tmp_path / "missing", output_path=tmp_path / "out.csv")
    assert result.empty
    assert (tmp_path / "out.csv").exists()


def test_normalized_international_match_table_has_required_columns(tmp_path):
    root = _synthetic_statsbomb(tmp_path / "statsbomb")
    result = build_international_match_dataset(root, competition_name="FIFA World Cup", season_id=106)
    required = {"match_id", "date", "competition_name", "home_team", "away_team", "neutral_site", "country_or_team_type", "data_mode", "has_event_data"}
    assert required.issubset(result.columns)
    assert result["country_or_team_type"].eq("national_team").all()


def test_club_and_international_ratings_are_not_mixed(tmp_path):
    root = _synthetic_statsbomb(tmp_path / "statsbomb")
    data = build_international_match_dataset(root)
    ratings = build_international_team_ratings(data, "2022-11-22")
    assert "Brazil" in ratings["team"].tolist()
    assert "Arsenal" not in ratings["team"].tolist()


def test_neutral_site_logic_reduces_home_advantage():
    neutral, _ = international_home_advantage("true")
    non_neutral, _ = international_home_advantage("false")
    unknown, flags = international_home_advantage("unknown")
    assert neutral < non_neutral
    assert neutral <= unknown <= non_neutral
    assert "neutral_site_unknown" in flags


def test_sparse_warning_and_prior_only_opponent_adjustment(tmp_path):
    root = _synthetic_statsbomb(tmp_path / "statsbomb")
    data = build_international_match_dataset(root)
    early = build_international_team_ratings(data, "2022-11-13")
    later = build_international_team_ratings(data, "2022-11-22")
    assert early["data_quality_flags"].str.contains("sparse_sample").any()
    assert later["matches_played"].sum() > early["matches_played"].sum()


def test_international_projection_outputs_required_fields_and_low_sparse_confidence(tmp_path):
    root = _synthetic_statsbomb(tmp_path / "statsbomb")
    data = build_international_match_dataset(root)
    row = project_international_match(data, "Brazil", "Morocco", "2022-11-13", neutral_site="true").iloc[0]
    required = {"team_a_xg_final", "team_b_xg_final", "team_a_win_prob", "confidence_score", "confidence_label", "risk_flags", "international_context_warnings", "data_mode"}
    assert required.issubset(row.index)
    assert 0 <= row["confidence_score"] <= 100
    assert row["confidence_label"] == "Low"


def test_event_style_fields_null_or_flagged_when_events_missing(tmp_path):
    root = _synthetic_statsbomb(tmp_path / "statsbomb")
    data = build_international_match_dataset(root)
    missing_event = data[~data["has_event_data"]].iloc[0]
    assert "missing_event_data" in missing_event["event_style_flags"]
    assert pd.isna(missing_event["home_xg_event"])


def test_international_backtest_runs_on_synthetic_fixtures(tmp_path):
    root = _synthetic_statsbomb(tmp_path / "statsbomb")
    data = build_international_match_dataset(root)
    result = run_international_backtest(data, "2022-11-14", "2022-11-21", output_dir=tmp_path, min_prior_matches=1)
    assert not result["results"].empty
    assert "International Backtest Summary" in result["summary"]


def test_international_cli_smoke(tmp_path):
    root = _synthetic_statsbomb(tmp_path / "statsbomb")
    output = tmp_path / "international.csv"
    list_cmd = subprocess.run([sys.executable, "-m", "src.cli", "list-international-competitions", "--statsbomb-root", str(root)], cwd=ROOT, capture_output=True, text=True, check=True)
    build_cmd = subprocess.run([sys.executable, "-m", "src.cli", "build-international-dataset", "--statsbomb-root", str(root), "--competition-name", "FIFA World Cup", "--season-id", "106", "--output", str(output)], cwd=ROOT, capture_output=True, text=True, check=True)
    project_cmd = subprocess.run([sys.executable, "-m", "src.cli", "project-international", "--input", str(output), "--team-a", "Brazil", "--team-b", "Morocco", "--as-of-date", "2022-11-22", "--neutral-site", "true", "--output", str(tmp_path / "projection.csv")], cwd=ROOT, capture_output=True, text=True, check=True)
    backtest_cmd = subprocess.run([sys.executable, "-m", "src.cli", "backtest-international", "--input", str(output), "--start-date", "2022-11-14", "--end-date", "2022-11-21", "--min-prior-matches", "1", "--output-dir", str(tmp_path)], cwd=ROOT, capture_output=True, text=True, check=True)
    assert "FIFA World Cup" in list_cmd.stdout
    assert "international match rows" in build_cmd.stdout
    assert "Brazil" in project_cmd.stdout
    assert "International Backtest Summary" in backtest_cmd.stdout


def test_confidence_scoring_valid_range_for_direct_call(tmp_path):
    root = _synthetic_statsbomb(tmp_path / "statsbomb")
    data = build_international_match_dataset(root)
    ratings = build_international_team_ratings(data, "2022-11-22").set_index("team")
    confidence = score_international_confidence(ratings.loc["Brazil"], ratings.loc["Morocco"], "true", data)
    assert 0 <= confidence["confidence_score"] <= 100

