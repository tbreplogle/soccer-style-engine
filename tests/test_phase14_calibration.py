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
    download_football_data_seasons,
    normalize_multi_season_football_data,
)
from src.models.confidence_hardening import ALLOWED_CONFIDENCE_RECOMMENDATIONS, run_confidence_hardening
from src.models.current_score_projection import DEFAULT_PROXY_ADJUSTMENT_CAP
from src.models.holdout_validation import ALLOWED_RECOMMENDATIONS, run_holdout_validation
from src.models.international_validation import run_international_validation
from src.models.leakage_audit import run_leakage_audit
from src.models.multi_season_validation import PROFILES, run_multi_season_validation


ROOT = Path(__file__).resolve().parents[1]


def _raw_csv(path: Path, team_prefix: str, start_year: int = 2021) -> Path:
    rows = []
    teams = [f"{team_prefix} Red", f"{team_prefix} Blue", f"{team_prefix} Green", f"{team_prefix} Gold"]
    for i in range(16):
        rows.append({
            "Date": f"{1 + (i % 24):02d}/08/{str(start_year)[-2:]}",
            "HomeTeam": teams[i % 4],
            "AwayTeam": teams[(i + 1) % 4],
            "FTHG": (i + 1) % 4,
            "FTAG": i % 3,
            "FTR": "H" if ((i + 1) % 4) > (i % 3) else "A" if ((i + 1) % 4) < (i % 3) else "D",
            "HS": 10 + i % 5,
            "AS": 8 + i % 4,
            "HST": 4 + i % 3,
            "AST": 3 + i % 3,
            "HC": 5 + i % 4,
            "AC": 4 + i % 4,
            "B365H": 1.8 + (i % 3) * 0.2,
            "B365D": 3.2,
            "B365A": 3.6,
            "B365>2.5": 1.95,
            "B365<2.5": 1.85,
        })
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _multi_season_raw(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    years = {"2122": 2021, "2223": 2022, "2324": 2023, "2425": 2024, "2526": 2025}
    for league in ["E0", "E1"]:
        for code, year in years.items():
            _raw_csv(root / f"{league}_{code}.csv", f"{league}{code}", year)
    return root


def _normalized(tmp_path: Path) -> pd.DataFrame:
    raw = _multi_season_raw(tmp_path / "raw")
    return normalize_multi_season_football_data(raw, tmp_path / "multi.csv")


def _statsbomb(root: Path) -> Path:
    (root / "matches" / "43").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    (root / "competitions.json").write_text(json.dumps([
        {"competition_id": 43, "season_id": 106, "competition_name": "FIFA World Cup", "season_name": "2022"},
    ]), encoding="utf-8")
    matches = []
    teams = ["Brazil", "Morocco", "France", "Argentina"]
    for i in range(8):
        matches.append({
            "match_id": 2000 + i,
            "match_date": f"2022-11-{10 + i:02d}",
            "home_team": {"home_team_name": teams[i % 4]},
            "away_team": {"away_team_name": teams[(i + 1) % 4]},
            "home_score": i % 3,
            "away_score": (i + 1) % 2,
            "competition_stage": {"name": "Group Stage"},
            "neutral_site": True,
        })
    (root / "matches" / "43" / "106.json").write_text(json.dumps(matches), encoding="utf-8")
    return root


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.payload


def test_multi_season_downloader_builds_urls_and_keeps_failed_rows(tmp_path, monkeypatch):
    assert build_football_data_url("2526", "E0") == "https://www.football-data.co.uk/mmz4281/2526/E0.csv"
    payload = b"Date,HomeTeam,AwayTeam,FTHG,FTAG\n01/08/25,A,B,1,0\n"

    def fake_urlopen(url, timeout=20):
        if url.endswith("/E1.csv"):
            raise OSError("synthetic failure")
        return _FakeResponse(payload)

    monkeypatch.setattr("src.data_ingestion.multi_league_football_data.urlopen", fake_urlopen)
    result = download_football_data_seasons(["2526"], ["E0", "E1"], tmp_path)
    assert result.loc[result["league_code"].eq("E0"), "status"].iloc[0] == "downloaded"
    assert result.loc[result["league_code"].eq("E1"), "status"].iloc[0] == "failed"
    assert (tmp_path / "E0_2526.csv").exists()


def test_multi_season_normalization_preserves_league_and_season(tmp_path):
    result = _normalized(tmp_path)
    assert {"league", "league_name", "season_code", "season_label", "downloaded_url"}.issubset(result.columns)
    assert set(result["league"]) == {"E0", "E1"}
    assert {"2122", "2223", "2324", "2425", "2526"}.issubset(set(result["season_code"].astype(str)))


def test_profile_validation_runs_without_mixing_league_season_groups(tmp_path):
    data = _normalized(tmp_path)
    result = run_multi_season_validation(data, "2021-08-01", "2026-05-31", min_matches=1, output_dir=tmp_path)
    full = result["results"][result["results"]["window"].eq("full")]
    assert not full.empty
    assert full.groupby(["league", "season_code"])["projection_profile"].nunique().min() == len(PROFILES)
    assert not full["league"].isna().any()
    assert not full["season_code"].isna().any()


def test_holdout_validation_does_not_use_test_data_for_selection(tmp_path):
    data = _normalized(tmp_path)
    result = run_holdout_validation(data, "2122,2223,2324", "2425", "2526", output_dir=tmp_path)
    assert result["recommendation"] in ALLOWED_RECOMMENDATIONS
    assert "test-season metrics were not used" in result["report"]
    assert result["selected_default_profile"] in PROFILES


def test_confidence_hardening_returns_allowed_recommendation_and_can_soften(tmp_path):
    data = _normalized(tmp_path)
    result = run_confidence_hardening(data, "2021-08-01", "2026-05-31", output_dir=tmp_path)
    assert result["recommendation"] in ALLOWED_CONFIDENCE_RECOMMENDATIONS
    soft = run_confidence_hardening(data.head(12), "2021-08-01", "2026-05-31", output_dir=tmp_path / "small")
    assert soft["recommendation"] in {"confidence_context_only", "hide_confidence_labels_until_calibrated"}


def test_leakage_audit_detects_future_leakage_and_passes_clean_data(tmp_path):
    data = _normalized(tmp_path)
    clean = run_leakage_audit(data, output_dir=tmp_path / "clean")
    assert clean["leakage_checks_passed"]
    bad = data.head(2).copy()
    bad["future_leakage_flag"] = [True, False]
    failed = run_leakage_audit(bad, output_dir=tmp_path / "bad")
    assert not failed["leakage_checks_passed"]
    assert failed["failed_checks"]


def test_international_validation_missing_and_historical_labeling(tmp_path):
    missing = run_international_validation(tmp_path / "missing", output_dir=tmp_path / "missing_report")
    assert missing["status"] == "local_data_missing"
    root = _statsbomb(tmp_path / "statsbomb")
    result = run_international_validation(root, competition_name="FIFA World Cup", season_id=106, output_dir=tmp_path / "intl_report")
    assert result["status"] == "evaluated"
    assert result["club_international_separation"]
    assert result["historical_event_labeling"] == "ok"


def test_phase14_cli_smoke(tmp_path):
    raw = _multi_season_raw(tmp_path / "raw")
    normalized = tmp_path / "multi.csv"
    reports = tmp_path / "reports"
    commands = [
        [sys.executable, "-m", "src.cli", "normalize-multi-season-football-data", "--input", str(raw), "--output", str(normalized)],
        [sys.executable, "-m", "src.cli", "validate-multi-season-profiles", "--input", str(normalized), "--start-date", "2021-08-01", "--end-date", "2026-05-31", "--min-matches", "1", "--output-dir", str(reports)],
        [sys.executable, "-m", "src.cli", "run-holdout-validation", "--input", str(normalized), "--train-seasons", "2122,2223,2324", "--validation-season", "2425", "--test-season", "2526", "--output-dir", str(reports)],
        [sys.executable, "-m", "src.cli", "harden-confidence", "--input", str(normalized), "--start-date", "2021-08-01", "--end-date", "2026-05-31", "--output-dir", str(reports)],
        [sys.executable, "-m", "src.cli", "audit-leakage", "--input", str(normalized), "--start-date", "2021-08-01", "--end-date", "2026-05-31", "--output-dir", str(reports)],
        [sys.executable, "-m", "src.cli", "validate-international", "--statsbomb-root", str(tmp_path / "missing_statsbomb"), "--output-dir", str(reports)],
    ]
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        assert completed.returncode == 0
    assert (reports / "multi_season_validation_summary.md").exists()
    assert (reports / "holdout_validation_summary.md").exists()
    assert (reports / "confidence_hardening_summary.md").exists()
    assert (reports / "leakage_audit_summary.md").exists()
    assert (reports / "international_validation_summary.md").exists()


def test_phase14_no_betting_fields_and_proxy_adjustments_disabled_by_default(tmp_path):
    data = _normalized(tmp_path)
    result = run_multi_season_validation(data, "2021-08-01", "2026-05-31", min_matches=1, output_dir=tmp_path)
    assert not any("betting" in col.lower() for col in result["results"].columns)
    assert DEFAULT_PROXY_ADJUSTMENT_CAP == 0.0
