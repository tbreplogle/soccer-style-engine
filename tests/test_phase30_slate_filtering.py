from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.projection_checkpoint import run_projection_checkpoint
from src.cli import build_parser
from src.international_current.current_international_slate import project_current_international
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.static_viewer import build_static_viewer


pytestmark = pytest.mark.quick


def _write_cache(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    fixtures = [
        ("past-1", "2026-06-24", "20:00", "Mexico", "South Africa"),
        ("today-1", "2026-06-25", "12:00", "Japan", "Canada"),
        ("today-2", "2026-06-25", "18:00", "France", "Germany"),
        ("future-1", "2026-06-27", "15:00", "Brazil", "Portugal"),
        ("future-2", "2026-07-03", "16:00", "Spain", "Italy"),
        ("placeholder-1", "2026-06-25", "21:00", "W100", "Runner-up Group A"),
    ]
    rows = [
        {
            "source_match_id": source_match_id,
            "match_date": match_date,
            "kickoff_time": kickoff_time,
            "competition": "FIFA World Cup",
            "round_name": "Group Stage",
            "group_name": "Group A",
            "home_team": home,
            "away_team": away,
            "neutral_site": "true",
            "status": "scheduled",
            "source_tier": "real",
            "reliability_status": "local_cache",
        }
        for source_match_id, match_date, kickoff_time, home, away in fixtures
    ]
    with (cache / "fixtures.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    teams = sorted({team for _, _, _, home, away in fixtures for team in [home, away] if not team.startswith("W") and "Runner-up" not in team})
    ratings = [
        {"team": team, "rating": str(1500 + index * 35), "rating_date": "2026-06-25", "rating_source": "synthetic_real_rating"}
        for index, team in enumerate(teams)
    ]
    with (cache / "ratings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ratings[0].keys()))
        writer.writeheader()
        writer.writerows(ratings)


def _project(tmp_path: Path, **kwargs):
    cache = tmp_path / "cache"
    output = tmp_path / "outputs" / "current_international"
    if not cache.exists():
        _write_cache(cache)
    return project_current_international(
        as_of_date=kwargs.pop("as_of_date", "2026-06-25"),
        cache_dir=cache,
        output_dir=output,
        max_matches=kwargs.pop("max_matches", 10),
        **kwargs,
    )


def test_today_window_selects_only_as_of_date_fixtures_and_skips_placeholders(tmp_path):
    result = _project(tmp_path, slate_window="today")

    projections = result["projections"]
    assert len(projections) == 2
    assert set(projections["fixture_date"]) == {"2026-06-25"}
    assert set(projections["fixture_temporal_status"]) == {"today"}
    assert set(projections["slate_window_status"]) == {"selected_today"}
    assert "W100" not in set(projections["team_a"])
    assert result["manifest"]["skipped_unresolved_fixtures"] == 1


def test_today_window_returns_no_rows_if_no_same_day_fixtures_exist(tmp_path):
    result = _project(tmp_path, as_of_date="2026-06-26", slate_window="today")

    assert result["projections"].empty
    assert result["manifest"]["selected_fixture_count"] == 0


def test_next_window_selects_next_future_fixture_date_when_today_has_none(tmp_path):
    result = _project(tmp_path, as_of_date="2026-06-26", slate_window="next")

    assert len(result["projections"]) == 1
    row = result["projections"].iloc[0]
    assert row["fixture_date"] == "2026-06-27"
    assert row["team_a"] == "Brazil"
    assert row["slate_window_status"] == "selected_next_upcoming"


def test_upcoming_window_respects_days_ahead_and_max_matches_after_filtering(tmp_path):
    result = _project(tmp_path, slate_window="upcoming", days_ahead=7, max_matches=1)

    assert len(result["projections"]) == 1
    assert result["manifest"]["selected_fixture_count"] == 3
    assert result["projections"].iloc[0]["fixture_date"] == "2026-06-25"
    skipped = pd.read_csv(tmp_path / "outputs" / "current_international" / "2026-06-25" / "slate_selection" / "skipped_by_date_fixtures.csv")
    assert "2026-07-03" in set(skipped["fixture_date"])


def test_date_range_respects_bounds_and_include_past(tmp_path):
    without_past = _project(
        tmp_path / "without",
        as_of_date="2026-06-25",
        slate_window="date_range",
        date_from="2026-06-24",
        date_to="2026-06-25",
    )
    with_past = _project(
        tmp_path / "with",
        as_of_date="2026-06-25",
        slate_window="date_range",
        date_from="2026-06-24",
        date_to="2026-06-25",
        include_past=True,
    )

    assert set(without_past["projections"]["fixture_date"]) == {"2026-06-25"}
    assert set(with_past["projections"]["fixture_date"]) == {"2026-06-24", "2026-06-25"}


def test_all_resolved_returns_resolved_fixtures_regardless_of_date(tmp_path):
    result = _project(tmp_path, slate_window="all-resolved")

    assert len(result["projections"]) == 5
    assert "2026-06-24" in set(result["projections"]["fixture_date"])
    assert "2026-07-03" in set(result["projections"]["fixture_date"])
    assert set(result["projections"]["fixture_resolution_status"]) == {"resolved"}


def test_selected_rows_are_sorted_by_date_and_kickoff(tmp_path):
    result = _project(tmp_path, slate_window="upcoming", days_ahead=10)

    pairs = list(zip(result["projections"]["fixture_date"], result["projections"]["kickoff_time"]))
    assert pairs == sorted(pairs)


def test_projection_output_contains_slate_fields_and_reports_are_written(tmp_path):
    result = _project(tmp_path, slate_window="next")
    projection_columns = set(result["projections"].columns)

    for column in [
        "fixture_date",
        "kickoff_time",
        "fixture_temporal_status",
        "is_current_slate",
        "slate_window_status",
        "slate_skip_reason",
        "slate_window",
        "selected_by_slate_filter",
    ]:
        assert column in projection_columns
    run_dir = tmp_path / "outputs" / "current_international" / "2026-06-25" / "slate_selection"
    assert (run_dir / "slate_selection_summary.md").exists()
    assert (run_dir / "selected_fixtures.csv").exists()
    assert (run_dir / "skipped_unresolved_fixtures.csv").exists()
    assert result["manifest"]["max_matches_applied_after_slate_filter"] is True


def test_checkpoint_passes_slate_options_through_and_viewer_shows_collapsible_board(tmp_path):
    cache = tmp_path / "cache"
    outputs = tmp_path / "outputs"
    _write_cache(cache)

    checkpoint = run_projection_checkpoint(
        as_of_date="2026-06-25",
        run_current_international=True,
        cache_dir=cache,
        output_dir=outputs / "projection_checkpoints",
        slate_window="next",
        max_matches=10,
        build_poisson_board=True,
    )
    viewer = build_static_viewer(outputs, outputs / "viewer")

    assert checkpoint["manifest"]["slate_window"] == "next"
    assert checkpoint["manifest"]["current_projection_slate_selection"]["selected_fixtures"] == 2
    assert checkpoint["poisson"] is not None
    board_html = (outputs / "viewer" / "projection_checkpoints" / "2026-06-25" / "index.html").read_text(encoding="utf-8")
    assert "Slate selection summary" in board_html
    assert "match-selector" in board_html
    assert "<details class=\"match-card\" id=\"match-1\" open>" in board_html
    assert "<details class=\"match-card\" id=\"match-2\">" in board_html
    assert "1X2:" in board_html
    assert "Likely:" in board_html
    assert "poisson_match_summary.csv" in board_html
    assert "Correct Score Grid" in board_html
    assert viewer["safety_scan_status"] == "pass"


def test_guardrails_and_cli_flags_remain_registered():
    commands = build_parser()._subparsers._group_actions[0].choices
    current = commands["project-current-international"]
    checkpoint = commands["projection-results-checkpoint"]
    assert "run-today" in commands
    assert "--slate-window" in current.format_help()
    assert "--include-past" in checkpoint.format_help()
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
    guardrail_payload = json.dumps({
        "current_statsbomb_used": False,
        "proxy_adjustments_enabled": False,
        "no_betting_recommendations": True,
    })
    assert "current_statsbomb_used" in guardrail_payload
    assert "no_betting_recommendations" in guardrail_payload
