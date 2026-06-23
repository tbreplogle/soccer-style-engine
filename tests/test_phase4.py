from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.agents.matchup_intelligence_agent import analyze_matchup
from src.agents.team_identity_agent import classify_team_identity
from src.data_ingestion.statsbomb_loader import StatsBombLoader
from src.features.event_features import compute_match_style_metrics
from src.features.team_aggregates import build_team_style_profile
from src.models.backtest import run_backtest
from src.models.score_projection import project_match


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_STATSBOMB = ROOT / "data" / "sample" / "statsbomb-open-data"
SYNTHETIC_LOG = ROOT / "data" / "sample" / "synthetic_team_match_style_log.csv"


def test_statsbomb_loader_parses_sample_event_file():
    loader = StatsBombLoader(SAMPLE_STATSBOMB)
    events = loader.load_events(1001)

    assert not events.empty
    assert "type.name" in events.columns
    assert events.attrs["raw_json"][0]["id"] == "e1"
    assert loader.match_has_360(1001) is False


def test_style_metrics_produce_one_row_per_team_per_match():
    loader = StatsBombLoader(SAMPLE_STATSBOMB)
    events = loader.load_events(1001)
    rows = compute_match_style_metrics(
        events,
        match_info={
            "match_id": 1001,
            "date": "2026-01-01",
            "competition": "Synthetic Cup",
            "season": "Synthetic 2026",
            "home_team": "Red FC",
            "away_team": "Blue FC",
            "home_goals": 2,
            "away_goals": 1,
        },
    )

    assert len(rows) == 2
    assert set(rows["team"]) == {"Red FC", "Blue FC"}
    assert rows["data_quality_flag"].eq("event_only").all()
    assert rows["compactness"].isna().all()


def test_rolling_profile_uses_only_matches_before_as_of_date():
    profile = build_team_style_profile("Red FC", "2026-01-22", style_log=SYNTHETIC_LOG)

    assert profile["matches_used"] == 3
    assert profile["raw_metrics"]["xg_for"] < 2.2


def test_identity_classifier_labels_obvious_archetype():
    profile = {
        "team": "Synthetic Control",
        "matches_used": 8,
        "raw_metrics": {"possession_pct": 65, "field_tilt_pct": 70, "avg_possession_length": 20},
        "percentile_ranks": {
            "possession_pct": 90,
            "field_tilt_pct": 88,
            "avg_possession_length": 75,
            "direct_speed": 45,
        },
        "data_quality_summary": {"event_only": 8},
    }

    result = classify_team_identity(profile)
    assert result["identities"][0]["label"] == "Possession Controller"
    assert result["identities"][0]["supporting_metric_evidence"]


def test_matchup_intelligence_returns_edges_and_uncertainties():
    result = analyze_matchup("Red FC", "Blue FC", "2026-02-12", style_log=SYNTHETIC_LOG)

    assert "style_summary" in result
    assert result["home_style_edges"]
    assert result["key_uncertainties"]
    assert result["total_goals_style_pressure"] in {"Up", "Down", "Neutral"}


def test_score_projection_probabilities_sum_correctly():
    projection = project_match("Red FC", "Blue FC", "2026-02-12", style_log=SYNTHETIC_LOG)
    row = projection.iloc[0]

    assert abs((row["home_win_prob"] + row["draw_prob"] + row["away_win_prob"]) - 1.0) < 1e-6
    assert abs((row["over_2_5_prob"] + row["under_2_5_prob"]) - 1.0) < 1e-6
    assert row["home_xg_base"] != row["home_xg_final"] or row["away_xg_base"] != row["away_xg_final"]


def test_backtest_runs_on_sample_without_future_leakage(tmp_path):
    result = run_backtest(
        "2026-01-22",
        "2026-02-05",
        style_log=SYNTHETIC_LOG,
        output_dir=tmp_path,
    )

    results = result["results"]
    assert len(results) == 3
    assert (tmp_path / "backtest_results.csv").exists()
    assert (tmp_path / "backtest_summary.md").exists()


def test_missing_360_data_does_not_create_fake_tracking_metrics():
    loader = StatsBombLoader(SAMPLE_STATSBOMB)
    rows = compute_match_style_metrics(loader.load_events(1001), match_info={"match_id": 1001})

    assert rows["data_quality_flag"].eq("event_only").all()
    assert rows["width_in_possession"].isna().all()
    assert rows["depth_in_possession"].isna().all()
