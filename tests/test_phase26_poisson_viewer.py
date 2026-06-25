from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.poisson_output import build_poisson_board_for_match
from src.cli import build_parser
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.run_index import build_run_index
from src.viewer.static_viewer import build_static_viewer

pytestmark = pytest.mark.quick


def _write_daily_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_dir.name,
        "run_date": run_dir.name,
        "generated_at": "2026-06-24T12:00:00+00:00",
        "status": "success",
        "currentness_status": "ok",
        "season_sanity_status": "ok",
        "leagues": ["E0"],
        "normalized_row_counts": {"total_rows": 4},
        "slate_type": "current_international_run",
        "warnings": [],
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "run_summary.md").write_text("# Daily Run\n\nNo warning rows.", encoding="utf-8")


def _board(home: str, away: str, source_tier: str, sample: bool = False) -> dict[str, pd.DataFrame]:
    return build_poisson_board_for_match(
        home_team=home,
        away_team=away,
        projected_home_xg=1.42 if home == "Curacao" else 1.18,
        projected_away_xg=0.95 if home == "Curacao" else 1.31,
        max_goals=4,
        metadata={
            "data_support_level": "low_manual_fixture_rating" if source_tier == "manual" else "sample_demo_only",
            "confidence_label": "low",
            "style_inputs_available": False,
            "is_sample_data": sample,
            "source_tier": source_tier,
            "rating_status": "rating_only",
            "primary_warning": "Rating-only projection. Style inputs are unavailable.",
            "source_warning": "Manual rows are user supplied." if source_tier == "manual" else "Sample/demo row.",
            "rating_warning": "Rating support is limited.",
            "style_warning": "No true event/tracking style inputs were used.",
            "guardrail_flags": "proxy adjustments disabled; current_statsbomb_used=false",
        },
    )


def _write_checkpoint(root: Path) -> Path:
    checkpoint_dir = root / "projection_checkpoints" / "2026-06-25"
    poisson_dir = checkpoint_dir / "poisson"
    poisson_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": "projection_checkpoint_2026-06-25",
        "run_date": "2026-06-25",
        "generated_at": "2026-06-25T12:00:00+00:00",
        "status": "pass",
        "rows_reviewed": 2,
        "real_rows_reviewed": 0,
        "manual_rows_reviewed": 1,
        "sample_rows_reviewed": 1,
        "warning_count": 2,
    }
    (checkpoint_dir / "projection_checkpoint_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (checkpoint_dir / "projection_checkpoint_summary.md").write_text(
        "# Projection Results Checkpoint\n\nProbability output review only.",
        encoding="utf-8",
    )
    (checkpoint_dir / "projection_checkpoint_rows.csv").write_text("team_a,team_b\nCuracao,Cote d'Ivoire\n", encoding="utf-8")
    (checkpoint_dir / "projection_checkpoint_flags.csv").write_text("team_a,team_b,warning\nCuracao,Cote d'Ivoire,low support\n", encoding="utf-8")
    (poisson_dir / "poisson_summary.md").write_text("# Poisson Summary\n\nGenerated from projected xG.", encoding="utf-8")

    boards = [
        _board("Curacao", "Cote d'Ivoire", "manual"),
        _board("Japan", "Chile", "sample", sample=True),
    ]
    for table_name, filename in [
        ("one_x_two", "poisson_1x2.csv"),
        ("totals", "poisson_totals.csv"),
        ("btts", "poisson_btts.csv"),
        ("clean_sheets", "poisson_clean_sheets.csv"),
        ("correct_score_matrix", "poisson_correct_score_matrix.csv"),
        ("match_summary", "poisson_match_summary.csv"),
    ]:
        pd.concat([board[table_name] for board in boards], ignore_index=True).to_csv(poisson_dir / filename, index=False)
    return checkpoint_dir


def test_poisson_board_viewer_builds_readable_checkpoint_page(tmp_path):
    outputs = tmp_path / "outputs"
    _write_daily_run(outputs / "runs" / "2026-06-24")
    _write_checkpoint(outputs)

    index = build_run_index(outputs)
    checkpoint = next(entry for entry in index if entry["entry_type"] == "projection_checkpoint")
    assert checkpoint["manual_rows_reviewed"] == 1
    assert checkpoint["sample_rows_reviewed"] == 1
    assert checkpoint["poisson_match_count"] == 2

    result = build_static_viewer(outputs, tmp_path / "viewer")
    assert result["runs_included"] == 2
    assert result["poisson_board_pages"]
    assert result["safety_scan_status"] == "pass"
    assert (tmp_path / "viewer" / "runs" / "2026-06-24.html").exists()

    index_html = (tmp_path / "viewer" / "index.html").read_text(encoding="utf-8")
    assert "projection_checkpoint" in index_html
    assert "current_international_run" in index_html
    assert "poisson matches" in index_html
    assert "projection_checkpoints/2026-06-25/index.html" in index_html

    detail_html = (tmp_path / "viewer" / "runs" / "projection_checkpoint_2026-06-25.html").read_text(encoding="utf-8")
    assert "Open readable Poisson probability board" in detail_html

    board_html = (tmp_path / "viewer" / "projection_checkpoints" / "2026-06-25" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "Curacao vs Cote d&#x27;Ivoire" in board_html
    assert "Projected xG" in board_html
    assert "Projected total" in board_html
    assert "Most likely score" in board_html
    assert "Model-implied American odds" in board_html
    assert "1X2 Probability Output" in board_html
    assert "2.5" in board_html
    assert "BTTS" in board_html
    assert "Clean Sheets" in board_html
    assert "Top Correct Scores" in board_html
    assert "Correct Score Grid" in board_html
    assert "Manual rows are user supplied and not source-verified." in board_html
    assert "Sample/demo rows are not real current matchups." in board_html
    assert "proxy adjustments disabled" in board_html
    assert "current_statsbomb_used=false" in board_html
    assert "poisson_match_summary.csv" in board_html
    assert "poisson_correct_score_matrix.csv" in board_html
    assert "1-0" not in board_html


def test_phase26_cli_guardrails_remain_in_place():
    commands = build_parser()._subparsers._group_actions[0].choices
    assert "build-report-viewer" in commands
    assert "run-today" in commands
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
