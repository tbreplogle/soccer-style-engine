from __future__ import annotations

import json
import subprocess
import sys
import shutil
from pathlib import Path

import pandas as pd
import pytest

import src.cli as cli
from src.analysis.poisson_output import build_poisson_board_for_match, probability_to_american_odds
from src.analysis.projection_checkpoint import analyze_projection_rows, run_projection_checkpoint
from src.international_current.current_international_schema import CurrentInternationalFixture, CurrentInternationalTeamRating
from src.international_current.rating_projection import project_from_fixture_and_ratings
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.run_index import build_run_index
from src.viewer.static_viewer import build_static_viewer


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.quick


def _seed_sample_current_cache(cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "data" / "sample" / "worldcup_static_fixtures_openfootball_sample.json", cache_dir / "fixtures.json")
    shutil.copyfile(ROOT / "data" / "sample" / "eloratings_sample.csv", cache_dir / "ratings.csv")


def _projection_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "team_a": "United States",
            "team_b": "Canada",
            "baseline_mode_used": "fixture_rating_only_baseline",
            "team_a_xg_final": 1.25,
            "team_b_xg_final": 1.10,
            "projected_total": 2.35,
            "most_likely_score": "1-1",
            "team_a_win_prob": 0.37,
            "draw_prob": 0.29,
            "team_b_win_prob": 0.34,
            "confidence_label": "Medium-Low",
            "confidence_score": 48,
            "data_mode": "fallback_rating_only",
            "data_support_level": "medium_current_fixture_rating",
            "source_tier": "real",
            "is_sample_data": False,
            "style_inputs_available": False,
            "style_inputs_warning": "No current event/xG/tracking/style-aware matchup inputs are available.",
            "rating_only_warning": "Rating-only baseline; no current style-aware matchup inputs.",
        },
        {
            "team_a": "France",
            "team_b": "Spain",
            "baseline_mode_used": "fixture_rating_only_baseline",
            "team_a_xg_final": -0.2,
            "team_b_xg_final": 3.2,
            "projected_total": 6.1,
            "most_likely_score": "",
            "team_a_win_prob": 0.50,
            "draw_prob": 0.30,
            "team_b_win_prob": 0.30,
            "confidence_label": "High",
            "confidence_score": 82,
            "data_mode": "fallback_rating_only",
            "data_support_level": "low_fixture_only",
            "source_tier": "real",
            "is_sample_data": False,
            "style_inputs_available": False,
            "warnings": "style adjustment applied",
        },
    ])


def test_projection_checkpoint_analyzer_flags_bad_rows():
    result = analyze_projection_rows(_projection_rows())
    flags = set(result["flags"]["flag_type"].tolist())
    assert result["summary"]["rows_reviewed"] == 2
    assert result["summary"]["status"] == "warning"
    assert "projected_total_out_of_range" in flags
    assert "negative_projected_home_xg" in flags
    assert "wdl_probability_sum_off" in flags
    assert "missing_most_likely_score" in flags
    assert "high_confidence_low_support" in flags
    assert "style_overclaim" in flags
    assert "missing_rating_only_warning" in flags


def test_projection_checkpoint_writes_outputs(tmp_path):
    projection_file = tmp_path / "projection.csv"
    _projection_rows().head(1).to_csv(projection_file, index=False)
    result = run_projection_checkpoint(
        as_of_date="2026-06-24",
        projection_file=projection_file,
        output_dir=tmp_path / "checkpoints",
    )
    assert result["status"] == "pass"
    assert result["summary_path"].exists()
    assert result["rows_path"].exists()
    assert result["flags_path"].exists()
    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    assert manifest["rows_reviewed"] == 1
    assert manifest["real_rows_reviewed"] == 1
    match_summary = pd.read_csv(tmp_path / "checkpoints" / "2026-06-24" / "poisson" / "poisson_match_summary.csv")
    assert (match_summary["most_likely_score"].str.contains(r"\d+ - \d+", regex=True)).all()
    assert not match_summary["most_likely_score"].str.contains(r"^\d+-\d+$", regex=True).any()
    assert "Baseline to Beat Next" in result["summary_path"].read_text(encoding="utf-8")


def test_projection_results_checkpoint_cli_smoke(tmp_path):
    projection_file = tmp_path / "projection.csv"
    _projection_rows().head(1).to_csv(projection_file, index=False)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "projection-results-checkpoint",
            "--as-of-date",
            "2026-06-24",
            "--projection-file",
            str(projection_file),
            "--output-dir",
            str(tmp_path / "checkpoints"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Status: pass" in result.stdout
    assert "Rows reviewed: 1 real rows, 0 manual rows, 0 sample/demo rows" in result.stdout
    assert "Poisson board: written" in result.stdout


def test_projection_checkpoint_can_run_current_international_no_network(tmp_path):
    cache_dir = tmp_path / "empty_cache"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "projection-results-checkpoint",
            "--as-of-date",
            "2026-06-24",
            "--run-current-international",
            "--no-network",
            "--max-matches",
            "5",
            "--cache-dir",
            str(cache_dir),
            "--output-dir",
            str(tmp_path / "projection_checkpoints"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Status: warning" in result.stdout
    assert "Rows reviewed: 0 real rows, 0 manual rows, 0 sample/demo rows" in result.stdout
    assert "No real current fixture source available" in (
        tmp_path / "projection_checkpoints" / "2026-06-24" / "projection_checkpoint_flags.csv"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "projection_checkpoints" / "2026-06-24" / "projection_checkpoint_summary.md").exists()


def test_projection_checkpoint_allows_sample_demo_but_marks_rows(tmp_path):
    cache_dir = tmp_path / "sample" / "cache"
    _seed_sample_current_cache(cache_dir)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "projection-results-checkpoint",
            "--as-of-date",
            "2026-06-24",
            "--run-current-international",
            "--no-network",
            "--allow-sample-data",
            "--max-matches",
            "5",
            "--slate-window",
            "all-resolved",
            "--build-poisson-board",
            "--cache-dir",
            str(cache_dir),
            "--output-dir",
            str(tmp_path / "projection_checkpoints"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Status: warning" in result.stdout
    assert "0 real rows, 0 manual rows, 3 sample/demo rows" in result.stdout
    rows = pd.read_csv(tmp_path / "projection_checkpoints" / "2026-06-24" / "projection_checkpoint_rows.csv")
    assert rows["is_sample_data"].all()
    assert set(rows["data_support_level"]) == {"sample_demo_only"}
    assert (tmp_path / "projection_checkpoints" / "2026-06-24" / "poisson" / "poisson_1x2.csv").exists()


def test_projection_checkpoint_manual_rows_are_not_sample(tmp_path):
    cache_dir = tmp_path / "empty_cache"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "projection-results-checkpoint",
            "--as-of-date",
            "2026-06-24",
            "--run-current-international",
            "--manual-matchups",
            str(ROOT / "data" / "sample" / "current_international_matchups.csv"),
            "--no-network",
            "--max-matches",
            "5",
            "--slate-window",
            "all-resolved",
            "--build-poisson-board",
            "--cache-dir",
            str(cache_dir),
            "--output-dir",
            str(tmp_path / "projection_checkpoints"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "0 real rows, 2 manual rows, 0 sample/demo rows" in result.stdout
    rows = pd.read_csv(tmp_path / "projection_checkpoints" / "2026-06-24" / "projection_checkpoint_rows.csv")
    assert not rows["is_sample_data"].any()
    assert set(rows["source_tier"]) == {"manual"}
    assert set(rows["data_support_level"]) == {"low_manual_fixture_rating"}


def test_poisson_probability_board_math_is_valid():
    board = build_poisson_board_for_match(
        home_team="Home",
        away_team="Away",
        projected_home_xg=1.4,
        projected_away_xg=1.1,
        max_goals=6,
    )
    one_x_two = board["one_x_two"].iloc[0]
    assert one_x_two["home_win_probability"] + one_x_two["draw_probability"] + one_x_two["away_win_probability"] == pytest.approx(1.0)
    assert {"home_american_odds", "draw_american_odds", "away_american_odds"}.issubset(board["one_x_two"].columns)
    totals = board["totals"]
    for _, row in totals.iterrows():
        assert row["over_probability"] + row["under_probability"] == pytest.approx(1.0)
        assert row["over_fair_odds"] > 1
        assert row["over_american_odds"]
    btts = board["btts"].iloc[0]
    assert btts["yes_probability"] + btts["no_probability"] == pytest.approx(1.0)
    assert btts["btts_yes_american_odds"]
    clean = board["clean_sheets"].iloc[0]
    assert 0 <= clean["home_clean_sheet_probability"] <= 1
    assert 0 <= clean["away_clean_sheet_probability"] <= 1
    assert "home_clean_sheet_american_odds" in board["clean_sheets"].columns
    assert not board["correct_score_matrix"].empty
    assert "correct_score_american_odds" in board["correct_score_matrix"].columns
    assert not board["correct_score_matrix"]["score_label"].str.contains(r"^\d+-\d+$", regex=True).any()
    assert board["match_summary"].iloc[0]["most_likely_score"]
    assert "home_win_american_odds" in board["match_summary"].columns
    assert "most_likely_score_american_odds" in board["match_summary"].columns


def test_american_odds_conversion_favorite_and_underdog():
    assert probability_to_american_odds(0.6) == "-150"
    assert probability_to_american_odds(0.4) == "+150"
    assert probability_to_american_odds(0) == ""
    assert probability_to_american_odds(None) == ""


def test_missing_rating_status_and_warnings_are_clear():
    fixture = CurrentInternationalFixture(
        source_name="manual_current_fixture",
        home_team="Home",
        away_team="Away",
        reliability_status="manual_fallback",
    )
    both_missing = project_from_fixture_and_ratings(fixture, None, None)
    assert both_missing["rating_status"] == "both_ratings_missing"
    assert both_missing["rating_warning"] == "Both team ratings missing; neutral baseline xG split used."
    one_missing = project_from_fixture_and_ratings(
        fixture,
        CurrentInternationalTeamRating(source_name="test", team="Home", rating_value=1820),
        None,
    )
    assert one_missing["rating_status"] == "away_rating_missing"
    assert "One team rating missing; fallback rating used for missing side." in one_missing["rating_warning"]


def test_poisson_markdown_includes_american_odds_and_safe_scores():
    board = build_poisson_board_for_match(
        home_team="Home",
        away_team="Away",
        projected_home_xg=1.4,
        projected_away_xg=1.1,
        max_goals=6,
    )
    from src.analysis.poisson_output import build_poisson_summary_markdown

    text = build_poisson_summary_markdown(board)
    assert "fair American odds" in text
    assert "1 - 0" in text or "1 - 1" in text or "0 - 0" in text
    assert "1-0" not in text


def test_projection_checkpoint_viewer_integration(tmp_path):
    projection_file = tmp_path / "projection.csv"
    _projection_rows().head(1).to_csv(projection_file, index=False)
    run_projection_checkpoint(
        as_of_date="2026-06-24",
        projection_file=projection_file,
        output_dir=tmp_path / "outputs" / "projection_checkpoints",
    )
    index = build_run_index(tmp_path / "outputs")
    assert index[0]["entry_type"] == "projection_checkpoint"
    viewer = build_static_viewer(tmp_path / "outputs", tmp_path / "viewer")
    detail = (tmp_path / "viewer" / "runs" / "projection_checkpoint_2026-06-24.html").read_text(encoding="utf-8")
    assert viewer["runs_included"] == 1
    assert "Projection Checkpoint Rows" in detail
    assert "Poisson Match Summary" in detail
    assert "Projection Results Checkpoint" in detail


def test_phase25_cli_command_and_guardrails():
    parser = cli.build_parser()
    assert "projection-results-checkpoint" in parser._subparsers._group_actions[0].choices
    source_text = (ROOT / "src" / "international_current" / "current_international_slate.py").read_text(encoding="utf-8")
    assert "proxy score adjustments remain disabled" in source_text.lower()
    assert "current_statsbomb_used=false" in source_text
    assert "best bet" not in source_text.lower()
    assert "betting pick" not in source_text.lower()
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False


def test_projection_checkpoint_outputs_are_ignored_by_git():
    result = subprocess.run(
        ["git", "check-ignore", "outputs/projection_checkpoints/2026-06-24/projection_checkpoint_summary.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
