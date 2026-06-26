from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.baseline_calibration import calibrate_baseline_projections, evaluate_projection_calibration
from src.cli import build_parser
from src.international_current.current_international_slate import project_current_international
from src.international_current.fixture_deduplication import deduplicate_fixtures
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.run_index import build_run_index
from src.viewer.static_viewer import build_static_viewer


pytestmark = pytest.mark.quick


def _fixture_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "match_date": "2026-06-25",
            "kickoff_time": "",
            "competition": "FIFA World Cup",
            "round_name": "Group Stage",
            "group_name": "Group A",
            "home_team": "Mexico",
            "away_team": "Canada",
            "neutral_site": "true",
            "source_fixture_name": "openfootball_worldcup",
            "source_tier": "real",
            "source_fixture_status": "scheduled",
            "is_resolved_fixture": True,
            "projection_eligible": True,
        },
        {
            "match_date": "2026-06-25",
            "kickoff_time": "18:00 UTC-5",
            "competition": "FIFA World Cup",
            "round_name": "",
            "group_name": "",
            "home_team": "Mexico",
            "away_team": "Canada",
            "neutral_site": "true",
            "source_fixture_name": "espn_scoreboard",
            "source_tier": "real",
            "source_fixture_status": "scheduled",
            "is_resolved_fixture": True,
            "projection_eligible": True,
        },
        {
            "match_date": "2026-06-25",
            "kickoff_time": "20:00",
            "competition": "FIFA World Cup",
            "round_name": "Group Stage",
            "group_name": "Group B",
            "home_team": "Japan",
            "away_team": "Sweden",
            "neutral_site": "true",
            "source_fixture_name": "openfootball_worldcup",
            "source_tier": "real",
            "source_fixture_status": "scheduled",
            "is_resolved_fixture": True,
            "projection_eligible": True,
        },
    ])


def _write_cache(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    fixtures = [
        ("of-mex-can", "2026-06-25", "", "Mexico", "Canada", "openfootball_worldcup"),
        ("espn-mex-can", "2026-06-25", "18:00 UTC-5", "Mexico", "Canada", "espn_scoreboard"),
        ("jpn-swe", "2026-06-25", "20:00", "Japan", "Sweden", "openfootball_worldcup"),
        ("placeholder", "2026-06-25", "22:00", "W100", "Runner-up Group A", "openfootball_worldcup"),
        ("future", "2026-06-27", "19:00", "Brazil", "Portugal", "openfootball_worldcup"),
    ]
    rows = [
        {
            "source_match_id": source_match_id,
            "match_date": match_date,
            "kickoff_time": kickoff,
            "competition": "FIFA World Cup",
            "round_name": "Group Stage",
            "group_name": "Group A",
            "home_team": home,
            "away_team": away,
            "neutral_site": "true",
            "status": "scheduled",
            "source_name": source,
            "source_tier": "real",
            "reliability_status": "local_cache",
        }
        for source_match_id, match_date, kickoff, home, away, source in fixtures
    ]
    with (cache / "fixtures.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    teams = ["Mexico", "Canada", "Japan", "Sweden", "Brazil", "Portugal"]
    ratings = [
        {"team": team, "rating": str(1600 + index * 40), "rating_date": "2026-06-25", "rating_source": "synthetic_real_rating"}
        for index, team in enumerate(teams)
    ]
    with (cache / "ratings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ratings[0].keys()))
        writer.writeheader()
        writer.writerows(ratings)


def test_exact_duplicate_is_deduped_and_better_source_is_kept():
    result = deduplicate_fixtures(_fixture_frame())
    kept = result["deduplicated"]
    duplicates = result["duplicates"]

    assert len(kept) == 2
    primary = kept[kept["home_team"].eq("Mexico")].iloc[0]
    assert primary["deduplication_status"] == "kept_primary"
    assert primary["primary_source"] == "espn_scoreboard"
    assert "openfootball_worldcup" in primary["duplicate_sources"]
    assert len(duplicates) == 1
    assert result["summary"]["duplicate_rows_skipped"] == 1


def test_non_duplicates_remain_and_swapped_neutral_duplicate_is_review_only():
    frame = _fixture_frame()
    swapped = frame.iloc[2].copy()
    swapped["source_fixture_name"] = "espn_scoreboard"
    swapped["home_team"] = "Sweden"
    swapped["away_team"] = "Japan"
    result = deduplicate_fixtures(pd.concat([frame, pd.DataFrame([swapped])], ignore_index=True))

    kept = result["deduplicated"]
    assert len(kept[kept["home_team"].isin(["Japan", "Sweden"])]) == 2
    assert set(kept[kept["home_team"].isin(["Japan", "Sweden"])]["deduplication_status"]) == {"possible_duplicate_review"}
    assert result["summary"]["possible_duplicate_review_rows"] == 2


def test_projection_dedupes_before_slate_filtering_and_max_matches(tmp_path):
    cache = tmp_path / "cache"
    output = tmp_path / "outputs" / "current_international"
    _write_cache(cache)

    result = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=cache,
        output_dir=output,
        slate_window="today",
        max_matches=1,
    )

    assert result["manifest"]["fixture_rows_before_dedupe"] == 5
    assert result["manifest"]["fixture_rows_after_dedupe"] == 4
    assert result["manifest"]["duplicate_rows_skipped"] == 1
    assert result["manifest"]["selected_fixture_count"] == 2
    assert len(result["projections"]) == 1
    assert "W100" not in set(result["projections"]["team_a"])
    row = result["projections"].iloc[0]
    assert row["deduplication_status"] in {"kept_primary", "unique"}
    assert "fixture_key" in result["projections"].columns
    assert (output / "2026-06-25" / "fixture_deduplication" / "fixture_deduplication_summary.md").exists()


def test_calibration_metrics_and_buckets_calculate_on_synthetic_rows():
    rows = pd.DataFrame([
        {"home_goals": 2, "away_goals": 1, "home_xg": 1.8, "away_xg": 0.9, "home_win_prob": 0.6, "draw_prob": 0.25, "away_win_prob": 0.15, "over_2_5_prob": 0.55, "most_likely_score": "2-1", "top_3_scores": "2-1|1-1|2-0"},
        {"home_goals": 0, "away_goals": 0, "home_xg": 1.1, "away_xg": 1.0, "home_win_prob": 0.35, "draw_prob": 0.3, "away_win_prob": 0.35, "over_2_5_prob": 0.42, "most_likely_score": "1-1", "top_3_scores": "1-1|0-0|1-0"},
        {"home_goals": 1, "away_goals": 3, "home_xg": 0.8, "away_xg": 1.9, "home_win_prob": 0.2, "draw_prob": 0.22, "away_win_prob": 0.58, "over_2_5_prob": 0.62, "most_likely_score": "1-2", "top_3_scores": "1-2|1-3|0-2"},
    ])
    result = evaluate_projection_calibration(rows)
    expected_log_loss = (-math.log(0.6) - math.log(0.3) - math.log(0.58)) / 3

    assert result["metrics"]["row_count"] == 3
    assert result["metrics"]["wdl_log_loss"] == pytest.approx(expected_log_loss)
    assert result["metrics"]["brier_score"] > 0
    assert not result["probability_buckets"].empty
    assert not result["totals_calibration"].empty
    assert result["metrics"]["most_likely_score_hit_rate"] == pytest.approx(1 / 3)
    assert result["metrics"]["top_3_correct_score_hit_rate"] == pytest.approx(1.0)


def test_blocked_and_diagnostic_calibration_outputs_are_written(tmp_path):
    blocked = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="international_historical",
        min_rows=50,
        output_dir=tmp_path / "calibration",
    )
    diagnostic = calibrate_baseline_projections(
        as_of_date="2026-06-25",
        data_source="current_international_results",
        min_rows=50,
        output_dir=tmp_path / "calibration_current",
    )

    assert blocked["status"] == "blocked_missing_historical_ratings"
    assert "historical_rating_snapshots_needed" in blocked["recommendations"] or "insufficient_data" in blocked["recommendations"]
    assert Path(blocked["paths"]["summary"]).exists()
    assert diagnostic["status"] == "blocked_missing_results"


def test_viewer_indexes_calibration_and_dedupe_counts(tmp_path):
    cache = tmp_path / "cache"
    outputs = tmp_path / "outputs"
    _write_cache(cache)
    project_current_international(as_of_date="2026-06-25", cache_dir=cache, output_dir=outputs / "current_international")
    calibrate_baseline_projections(as_of_date="2026-06-25", data_source="international_historical", output_dir=outputs / "calibration")

    entries = build_run_index(outputs)
    assert any(entry["entry_type"] == "baseline_calibration" for entry in entries)
    current = next(entry for entry in entries if entry["entry_type"] == "current_international_run")
    assert current["duplicate_rows_skipped"] == 1
    viewer = build_static_viewer(outputs, outputs / "viewer")
    html = (outputs / "viewer" / "index.html").read_text(encoding="utf-8")
    assert "baseline_calibration" in html
    assert "dedupe" in html
    assert viewer["safety_scan_status"] == "pass"


def test_cli_and_guardrails_remain_registered():
    commands = build_parser()._subparsers._group_actions[0].choices
    assert "calibrate-baseline-projections" in commands
    assert "run-today" in commands
    assert "--dedupe-fixtures" in commands["project-current-international"].format_help()
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
    payload = json.dumps({
        "current_statsbomb_live_data_used": False,
        "proxy_adjustments_enabled": False,
        "no_betting_recommendations": True,
    })
    assert "current_statsbomb_live_data_used" in payload
    assert "no_betting_recommendations" in payload
