from __future__ import annotations

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.operational.daily_runner import run_daily_pipeline
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.run_index import build_run_index
from src.viewer.static_viewer import build_static_viewer, scan_report_safety


ROOT = Path(__file__).resolve().parents[1]


def _write_manifest(run_dir: Path, **overrides) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_dir.name,
        "run_date": run_dir.name,
        "generated_at": "2026-06-24T12:00:00+00:00",
        "status": "success_with_warnings",
        "currentness_status": "season_completed",
        "season_sanity_status": "ok",
        "leagues": ["E0"],
        "normalized_row_counts": {"total_rows": 12},
        "slate_type": "historical_validation_slate",
        "warnings": ["E0 appears season-complete, not stale."],
        "generated_output_paths": [],
    }
    manifest.update(overrides)
    path = run_dir / "run_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_run_files(run_dir: Path) -> None:
    _write_manifest(run_dir)
    (run_dir / "run_summary.md").write_text(
        "# Daily Pipeline Run Summary\n\nData currentness status: `season_completed`\n\n## Warning Groups\n\n- E0 appears season-complete, not stale.\n\nNo betting recommendation.",
        encoding="utf-8",
    )
    pd.DataFrame([{"home_team": "Arsenal", "away_team": "Chelsea", "projection_profile": "score_projection"}]).to_csv(
        run_dir / "club_slate_projections.csv",
        index=False,
    )
    pd.DataFrame([{"team_a": "France", "team_b": "Spain", "projection_profile": "international_score_projection"}]).to_csv(
        run_dir / "international_slate_projections.csv",
        index=False,
    )
    pd.DataFrame([{"projection_profile": "winner_probability", "home_win_probability": 0.42}]).to_csv(
        run_dir / "projection_profile_comparison.csv",
        index=False,
    )


def _raw_csv(path: Path, rows: int = 12) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    base = pd.Timestamp("2026-05-01")
    teams = ["Red FC", "Blue FC", "Green FC", "Yellow FC"]
    records = []
    for i in range(rows):
        records.append({
            "Date": (base + pd.Timedelta(days=i)).strftime("%d/%m/%y"),
            "HomeTeam": teams[i % 4],
            "AwayTeam": teams[(i + 1) % 4],
            "FTHG": i % 3,
            "FTAG": (i + 1) % 3,
            "FTR": "H",
            "HS": 10,
            "AS": 8,
            "HST": 4,
            "AST": 3,
            "HC": 5,
            "AC": 4,
            "B365H": 2.0,
            "B365D": 3.2,
            "B365A": 3.6,
        })
    pd.DataFrame(records).to_csv(path, index=False)
    return path


def test_run_index_handles_missing_and_empty_runs_folder(tmp_path):
    assert build_run_index(tmp_path / "missing") == []
    empty_root = tmp_path / "runs"
    empty_root.mkdir()
    assert build_run_index(empty_root) == []
    (empty_root / "2026-05-25").mkdir()
    index = build_run_index(empty_root)
    assert index[0]["status"] == "empty_run_folder"


def test_run_index_reads_valid_manifest_and_malformed_manifest(tmp_path):
    runs = tmp_path / "runs"
    _write_manifest(runs / "2026-05-25")
    bad = runs / "2026-05-24"
    bad.mkdir(parents=True)
    (bad / "run_manifest.json").write_text("{bad json", encoding="utf-8")
    index = build_run_index(runs)
    assert any(item["run_id"] == "2026-05-25" and item["row_count"] == 12 for item in index)
    assert any(item["status"] == "malformed_manifest" for item in index)


def test_static_viewer_creates_index_and_includes_run_outputs(tmp_path):
    runs = tmp_path / "runs"
    _write_run_files(runs / "2026-05-25")
    result = build_static_viewer(runs, tmp_path / "viewer")
    html = Path(result["viewer_output_path"]).read_text(encoding="utf-8")
    detail = (tmp_path / "viewer" / "runs" / "2026-05-25.html").read_text(encoding="utf-8")
    assert result["runs_included"] == 1
    assert "season_completed" in html
    assert "E0 appears season-complete" in detail
    assert "Arsenal" in detail
    assert "France" in detail
    assert "winner_probability" in detail


def test_safety_scan_flags_action_language_but_allows_disclaimers(tmp_path):
    ok = tmp_path / "ok.md"
    risky = tmp_path / "risky.md"
    ok.write_text("No betting recommendation. Market gap is not a betting signal.", encoding="utf-8")
    risky.write_text("This is a lock and a pick.", encoding="utf-8")
    assert scan_report_safety([ok])["safety_scan_status"] == "pass"
    result = scan_report_safety([ok, risky])
    assert result["safety_scan_status"] == "warning"
    assert "lock" in result["safety_warnings"][0] or "pick" in result["safety_warnings"][0]


def test_viewer_cli_smoke_tests(tmp_path):
    runs = tmp_path / "runs"
    _write_run_files(runs / "2026-05-25")
    viewer = tmp_path / "viewer"
    listed = subprocess.run(
        [sys.executable, "-m", "src.cli", "list-runs", "--runs-root", str(runs)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    built = subprocess.run(
        [sys.executable, "-m", "src.cli", "build-report-viewer", "--runs-root", str(runs), "--output-dir", str(viewer)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    opened = subprocess.run(
        [sys.executable, "-m", "src.cli", "open-report-viewer", "--viewer", str(viewer / "index.html")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "2026-05-25" in listed.stdout
    assert "Viewer output:" in built.stdout
    assert "Open this local file in a browser:" in opened.stdout


def test_daily_runner_supports_build_viewer(tmp_path):
    raw = tmp_path / "raw"
    _raw_csv(raw / "E0_2526.csv")
    result = run_daily_pipeline(
        "2026-05-12",
        season_code="2526",
        leagues="E0",
        output_root=tmp_path / "runs",
        slate_type="historical",
        max_matches=1,
        skip_download=True,
        skip_profile_comparison=True,
        raw_input_dir=raw,
        processed_output=tmp_path / "processed.csv",
        run_log_dir=tmp_path / "logs",
        build_viewer=True,
        viewer_output_dir=tmp_path / "viewer",
    )
    assert result["viewer"]["runs_included"] == 1
    assert Path(result["viewer"]["viewer_output_path"]).exists()
    assert result["manifest"]["viewer_output_path"] == str(tmp_path / "viewer" / "index.html")
    assert "Static viewer:" in Path(result["summary_path"]).read_text(encoding="utf-8")


def test_generated_viewer_outputs_are_ignored_by_git():
    result = subprocess.run(["git", "check-ignore", "outputs/viewer/index.html"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0


def test_viewer_does_not_recompute_models_and_guardrails_remain():
    viewer_code = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src" / "viewer").glob("*.py"))
    assert "src.models" not in viewer_code
    assert "project_current_match" not in viewer_code
    assert "build_club_slate_report" not in viewer_code
    assert "best bet" not in viewer_code.lower()
    assert "betting pick" not in viewer_code.lower()
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False
