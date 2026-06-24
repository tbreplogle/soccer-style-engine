from __future__ import annotations

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.data_ingestion.multi_league_football_data import (
    build_football_data_url,
    download_football_data_leagues,
    normalize_multi_league_football_data,
)
from src.models.confidence_calibration import ALLOWED_CONFIDENCE_RECOMMENDATIONS, audit_confidence_calibration
from src.models.international_readiness import audit_international_readiness
from src.models.multi_league_diagnostics import run_multi_league_profile_diagnostics


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample" / "football-data" / "sample_current_results.csv"


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return self.payload


def _multi_league_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "football-data"
    folder.mkdir()
    raw = SAMPLE.read_text(encoding="utf-8")
    (folder / "E0_2526.csv").write_text(raw, encoding="utf-8")
    changed = raw.replace("Red FC", "Red FC B").replace("Blue FC", "Blue FC B")
    (folder / "E1_2526.csv").write_text(changed, encoding="utf-8")
    return folder


def test_downloader_builds_urls_and_handles_failed_leagues(monkeypatch, tmp_path):
    assert build_football_data_url("2526", "E0").endswith("/2526/E0.csv")
    payload = b"Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n01/01/26,A,B,1,0,H\n"

    def fake_urlopen(url, timeout=20):
        if url.endswith("/E0.csv"):
            return _FakeResponse(payload)
        raise OSError("offline")

    monkeypatch.setattr("src.data_ingestion.multi_league_football_data.urlopen", fake_urlopen)
    result = download_football_data_leagues("2526", ["E0", "E1"], fallback_season_code="2425", output_dir=tmp_path)
    statuses = result.set_index("league_code")["status"].to_dict()
    assert statuses["E0"] == "downloaded"
    assert statuses["E1"] == "failed"


def test_multi_league_normalization_preserves_league_boundaries(tmp_path):
    folder = _multi_league_folder(tmp_path)
    result = normalize_multi_league_football_data(folder, season="2025-2026")
    assert set(result["league"]) == {"E0", "E1"}
    assert "league_name" in result.columns
    assert result.groupby("league")["home_team"].nunique().min() > 0


def test_diagnostics_do_not_mix_teams_across_leagues(tmp_path):
    data = normalize_multi_league_football_data(_multi_league_folder(tmp_path), season="2025-2026")
    result = run_multi_league_profile_diagnostics(data, "2026-01-15", "2026-02-15", profiles=["score_projection"], output_dir=tmp_path, min_matches=1)
    rows = result["results"]
    assert set(rows["league"]) == {"E0", "E1"}
    assert rows.groupby("league")["matches"].sum().gt(0).all()


def test_confidence_calibration_recommendation_and_unstable_buckets(tmp_path):
    buckets = pd.DataFrame(
        [
            {"league": "E0", "confidence_label": "High", "matches": 20, "total_goals_mae": 1.6, "wdl_log_loss": 1.2},
            {"league": "E0", "confidence_label": "Medium", "matches": 25, "total_goals_mae": 1.1, "wdl_log_loss": 1.0},
            {"league": "E1", "confidence_label": "High", "matches": 20, "total_goals_mae": 1.5, "wdl_log_loss": 1.1},
            {"league": "E1", "confidence_label": "Medium", "matches": 25, "total_goals_mae": 1.2, "wdl_log_loss": 1.0},
        ]
    )
    result = audit_confidence_calibration(buckets, output_dir=tmp_path)
    assert result["recommended_confidence_language"] in ALLOWED_CONFIDENCE_RECOMMENDATIONS
    assert result["recommended_confidence_language"] in {"needs_more_data", "confidence_context_only"}


def test_international_readiness_missing_statsbomb(tmp_path):
    result = audit_international_readiness(tmp_path / "missing", output_dir=tmp_path)
    assert result["available_international_competitions"] == []
    assert "not found" in result["setup_note"]


def test_international_readiness_identifies_synthetic_competition(tmp_path):
    root = tmp_path / "statsbomb"
    (root / "matches" / "43").mkdir(parents=True)
    (root / "events").mkdir()
    (root / "three-sixty").mkdir()
    (root / "competitions.json").write_text(json.dumps([{"competition_id": 43, "season_id": 3, "competition_name": "FIFA World Cup", "season_name": "2022"}]), encoding="utf-8")
    (root / "matches" / "43" / "3.json").write_text(json.dumps([{"match_id": 123}]), encoding="utf-8")
    (root / "events" / "123.json").write_text("[]", encoding="utf-8")
    (root / "three-sixty" / "123.json").write_text("[]", encoding="utf-8")
    result = audit_international_readiness(root, output_dir=tmp_path)
    assert result["available_international_competitions"][0]["competition_name"] == "FIFA World Cup"
    assert result["event_data_available"] is True
    assert result["three_sixty_available"] is True


def test_phase11_cli_smoke(tmp_path):
    folder = _multi_league_folder(tmp_path)
    output = tmp_path / "multi.csv"
    normalized = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "normalize-multi-league-football-data",
            "--input",
            str(folder),
            "--output",
            str(output),
            "--season",
            "2025-2026",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    diagnostics = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "diagnose-multi-league-profiles",
            "--input",
            str(output),
            "--start-date",
            "2026-01-15",
            "--end-date",
            "2026-02-15",
            "--profiles",
            "score_projection",
            "--min-matches",
            "1",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    audit = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "audit-international-readiness",
            "--statsbomb-root",
            str(tmp_path / "missing-statsbomb"),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "multi-league" in normalized.stdout
    assert "Multi-League Projection Profile Diagnostics" in diagnostics.stdout
    assert "International Readiness Audit" in audit.stdout


def test_raw_data_paths_are_gitignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/raw/" in gitignore
    assert "data/processed/*" in gitignore

