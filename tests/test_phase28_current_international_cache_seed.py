from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.cli import build_parser
from src.international_current.current_international_slate import project_current_international
from src.international_current.fixture_harvest import harvest_current_international_fixtures
from src.international_current.rating_harvest import harvest_current_international_ratings
from src.international_current.sources.cache_seed import seed_current_international_cache
from src.international_current.sources.eloratings_connector import parse_eloratings_rows
from src.international_current.sources.eloratings_connector import parse_eloratings_team_dictionary, validate_rating_frame
from src.international_current.sources.espn_connector import parse_espn_fixture_rows
from src.international_current.sources.fbref_connector import parse_fbref_fixture_rows, parse_fbref_stat_rows
from src.international_current.sources.international_football_connector import parse_international_football_ratings
from src.international_current.sources.openfootball_connector import parse_openfootball_rows
from src.international_current.sources.source_fetching import fetch_public_source
from src.international_current.team_name_normalization import normalize_team_name
from src.operational.defaults import OPERATIONAL_DEFAULTS
from src.viewer.static_viewer import build_static_viewer

pytestmark = pytest.mark.quick

ROOT = Path(__file__).resolve().parents[1]


def _write_raw_sources(raw: Path) -> dict[str, Path]:
    raw.mkdir(parents=True, exist_ok=True)
    openfootball = raw / "openfootball.json"
    openfootball.write_text(json.dumps({
        "matches": [
            {
                "date": "2026-06-25",
                "time": "18:00",
                "competition": "FIFA World Cup",
                "round": "Group Stage",
                "group": "Group E",
                "team1": "USA",
                "team2": "Ivory Coast",
                "venue": "Test Stadium",
            }
        ]
    }), encoding="utf-8")
    espn = raw / "espn.json"
    espn.write_text(json.dumps({
        "leagues": [{"name": "FIFA World Cup"}],
        "events": [{
            "date": "2026-06-25T21:00Z",
            "competitions": [{
                "neutralSite": True,
                "venue": {"fullName": "Second Stadium"},
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "Turkiye"}},
                    {"homeAway": "away", "team": {"displayName": "Korea Republic"}},
                ],
            }],
        }],
    }), encoding="utf-8")
    fbref_schedule = raw / "fbref_schedule.html"
    fbref_schedule.write_text(
        "<table><thead><tr><th>Date</th><th>Time</th><th>Home</th><th>Away</th><th>Venue</th></tr></thead>"
        "<tbody><tr><td>2026-06-26</td><td>18:00</td><td>Netherlands</td><td>Japan Men</td><td>Third Stadium</td></tr></tbody></table>",
        encoding="utf-8",
    )
    elo_csv = raw / "elo.csv"
    elo_csv.write_text(
        "team,rating,rating_date\nUnited States,1840,2026-06-24\nCote d'Ivoire,1760,2026-06-24\nTurkiye,1710,2026-06-24\nSouth Korea,1690,2026-06-24\nNetherlands,1820,2026-06-24\nJapan,1735,2026-06-24\n",
        encoding="utf-8",
    )
    intl_html = raw / "international_football.html"
    intl_html.write_text("<table><tr><th>Team</th><th>Rating</th></tr><tr><td>England Men</td><td>1815</td></tr></table>", encoding="utf-8")
    fbref_stats = raw / "fbref_stats.html"
    fbref_stats.write_text(
        "<table><tr><th>Squad</th><th>GF</th><th>GA</th><th>Sh</th><th>SoT</th></tr>"
        "<tr><td>United States</td><td>1.8</td><td>0.9</td><td>12</td><td>5</td></tr>"
        "<tr><td>Cote d'Ivoire</td><td>1.5</td><td>1.1</td><td>10</td><td>4</td></tr></table>",
        encoding="utf-8",
    )
    return {
        "openfootball": openfootball,
        "espn": espn,
        "fbref_schedule": fbref_schedule,
        "elo": elo_csv,
        "international_football": intl_html,
        "fbref_stats": fbref_stats,
    }


def test_phase28_parsers_handle_synthetic_sources(tmp_path):
    paths = _write_raw_sources(tmp_path)
    assert parse_openfootball_rows(paths["openfootball"].read_text(encoding="utf-8")).iloc[0]["home_team"] == "United States"
    assert parse_espn_fixture_rows(paths["espn"].read_text(encoding="utf-8")).iloc[0]["away_team"] == "South Korea"
    assert parse_fbref_fixture_rows(paths["fbref_schedule"].read_text(encoding="utf-8")).iloc[0]["away_team"] == "Japan"
    assert parse_eloratings_rows(paths["elo"].read_text(encoding="utf-8"))["normalized_team_name"].isin(["Cote d'Ivoire"]).any()
    assert parse_international_football_ratings(paths["international_football"].read_text(encoding="utf-8")).iloc[0]["normalized_team_name"] == "England"
    stats = parse_fbref_stat_rows(paths["fbref_stats"].read_text(encoding="utf-8"))
    assert stats["xg_for_per_match"].isna().all()
    assert stats["shots_for_per_match"].notna().all()


def test_cache_seed_writes_metadata_and_project_uses_seeded_real_cache(tmp_path):
    raw = _write_raw_sources(tmp_path / "raw")
    cache = tmp_path / "cache"
    output = tmp_path / "outputs" / "current_international"
    seed = seed_current_international_cache(
        as_of_date="2026-06-25",
        allow_network=False,
        seed_all=True,
        cache_dir=cache,
        output_dir=output,
        local_fixture_paths={
            "openfootball_worldcup": [raw["openfootball"]],
            "espn_scoreboard": [raw["espn"]],
            "fbref_schedule": [raw["fbref_schedule"]],
        },
        local_rating_paths={
            "eloratings": [raw["elo"]],
            "international_football_elo": [raw["international_football"]],
        },
        local_stat_paths={"fbref_team_stats": [raw["fbref_stats"]]},
    )
    assert len(seed["fixtures"]) == 3
    assert len(seed["ratings"]) == 7
    assert len(seed["stats"]) == 2
    assert Path(seed["paths"]["cache_seed_summary"]).exists()
    assert Path(seed["cache_paths"]["fixtures"]).exists()
    assert (raw["openfootball"].with_suffix(".json.metadata.json")).exists()

    fixtures = harvest_current_international_fixtures(as_of_date="2026-06-25", cache_dir=cache)
    ratings = harvest_current_international_ratings(
        fixture_teams=sorted(set(fixtures["fixtures_frame"]["home_team"]).union(fixtures["fixtures_frame"]["away_team"])),
        cache_dir=cache,
    )
    assert len(fixtures["fixtures_frame"]) == 3
    assert ratings["missing_rating_teams"] == []

    projection = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=cache,
        output_dir=output,
        strict_real_data=True,
        build_poisson_board=True,
    )
    assert projection["manifest"]["strict_real_data_status"] == "pass"
    assert projection["manifest"]["real_fixture_count"] == 3
    assert len(projection["projections"]) == 3
    assert projection["projections"]["data_coverage_score"].max() >= 70
    assert (output / "2026-06-25" / "poisson" / "poisson_match_summary.csv").exists()

    viewer = build_static_viewer(tmp_path / "outputs", tmp_path / "viewer")
    assert viewer["runs_included"] == 1
    detail = (tmp_path / "viewer" / "runs" / "current_international_2026-06-25.html").read_text(encoding="utf-8")
    assert "Cache Seed" in detail or "Source Fetch Results" in detail


def test_seed_command_no_network_creates_expected_outputs(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "seed-current-international-cache",
            "--as-of-date",
            "2026-06-25",
            "--all",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--output-dir",
            str(tmp_path / "outputs"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Fixture rows parsed: 0" in result.stdout
    run_dir = tmp_path / "outputs" / "2026-06-25" / "cache_seed"
    assert (run_dir / "cache_seed_summary.md").exists()
    assert (run_dir / "source_fetch_results.csv").exists()
    fetch_results = pd.read_csv(run_dir / "source_fetch_results.csv")
    assert "cache_miss" in set(fetch_results["status"])


def test_fetch_failure_is_a_result_not_exception(tmp_path):
    fetch, text = fetch_public_source(
        source_name="synthetic_missing",
        source_url="https://example.invalid/nope.csv",
        raw_dir=tmp_path / "raw",
        allow_network=False,
    )
    assert text == ""
    assert fetch.status == "cache_miss"
    assert Path(fetch.metadata_path).exists()


def test_strict_projection_fails_when_seeded_ratings_missing(tmp_path):
    raw = _write_raw_sources(tmp_path / "raw")
    cache = tmp_path / "cache"
    output = tmp_path / "outputs"
    seed_current_international_cache(
        as_of_date="2026-06-25",
        allow_network=False,
        seed_fixtures=True,
        cache_dir=cache,
        output_dir=output,
        local_fixture_paths={"openfootball_worldcup": [raw["openfootball"]]},
    )
    result = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=cache,
        output_dir=output,
        strict_real_data=True,
    )
    assert result["manifest"]["strict_real_data_status"] == "fail"
    assert result["manifest"]["teams_missing_ratings_count"] == 2


def test_phase28_cli_aliases_and_guardrails():
    commands = build_parser()._subparsers._group_actions[0].choices
    assert "seed-current-international-cache" in commands
    assert "run-today" in commands
    assert normalize_team_name("China PR").normalized_name == "China"
    assert normalize_team_name("Republic of Ireland").normalized_name == "Ireland"
    assert OPERATIONAL_DEFAULTS.club.proxy_adjustments_enabled is False


def test_rating_parser_handles_public_eloratings_tsv_with_dictionary():
    dictionary = parse_eloratings_team_dictionary(
        "AR\tArgentina\nES\tSpain\nFR\tFrance\nEN\tEngland\nBR\tBrazil\nDE\tGermany\n"
        "NL\tNetherlands\nMX\tMexico\nUS\tUnited States\tUSA\nJP\tJapan\n"
    )
    rows = [
        f"{idx}\t{idx}\t{code}\t{2100 - idx}\t1\t2200"
        for idx, code in enumerate(["AR", "ES", "FR", "EN", "BR", "DE", "NL", "MX", "US", "JP"], start=1)
    ]
    rows.extend(f"{idx}\t{idx}\tT{idx}\t{1700 - idx}\t1\t1800" for idx in range(11, 51))
    dictionary.update({f"T{idx}": f"Exampleland {idx}" for idx in range(11, 51)})

    frame = parse_eloratings_rows("\n".join(rows), source_url="https://www.eloratings.net/World.tsv", team_dictionary=dictionary)
    validation = validate_rating_frame(frame)

    assert len(frame) == 50
    assert validation["parse_status"] == "success"
    assert {"Argentina", "Spain", "Japan"}.issubset(set(frame["normalized_team_name"]))


def test_international_football_parser_handles_ranked_tables_and_text_fallback():
    html = (
        "<table class='elorank'>"
        "<tr><th><strong>1</strong>.</th><td><img title='Spain'></td><td>Spain</td><td>2134</td></tr>"
        "<tr><th><strong>2</strong>.</th><td><img title='Argentina'></td><td>Argentina</td><td>2144</td></tr>"
        "</table>"
    )
    table_frame = parse_international_football_ratings(html, source_url="https://www.international-football.net/elo-ratings-table")
    text_frame = parse_eloratings_rows("1 Spain 2134\n2 Argentina 2144\n3 United States 1769\n", source_url="synthetic-text")

    assert table_frame.set_index("normalized_team_name").loc["Spain", "rating"] == 2134
    assert text_frame.set_index("normalized_team_name").loc["United States", "rating"] == 1769


def test_low_coverage_rating_parse_is_flagged_and_diagnostic_is_written(tmp_path):
    rating_file = tmp_path / "ratings.html"
    rating_file.write_text("<table><tr><th>Team</th><th>Rating</th></tr><tr><td>Spain</td><td>2134</td></tr></table>", encoding="utf-8")

    seed = seed_current_international_cache(
        as_of_date="2026-06-25",
        allow_network=False,
        seed_ratings=True,
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "outputs",
        local_rating_paths={"international_football_elo": [rating_file]},
        max_sources=1,
    )

    fetch_results = seed["fetch_results"]
    assert "parse_error_or_low_coverage" in set(fetch_results["status"])
    diagnostics = pd.read_csv(seed["paths"]["rating_parse_diagnostics"])
    row = diagnostics[diagnostics["source_url"].astype(str).str.contains("ratings.html")].iloc[0]
    assert row["row_count"] == 1
    assert "Argentina" in row["expected_common_teams_missing"]


def test_project_uses_rating_cache_and_varies_projection_when_ratings_differ(tmp_path):
    raw = _write_raw_sources(tmp_path / "raw")
    cache = tmp_path / "cache"
    output = tmp_path / "outputs"
    seed_current_international_cache(
        as_of_date="2026-06-25",
        allow_network=False,
        seed_all=True,
        cache_dir=cache,
        output_dir=output,
        local_fixture_paths={"openfootball_worldcup": [raw["openfootball"]]},
        local_rating_paths={"eloratings": [raw["elo"]]},
        local_stat_paths={"fbref_team_stats": [raw["fbref_stats"]]},
        max_sources=1,
    )

    projection = project_current_international(
        as_of_date="2026-06-25",
        cache_dir=cache,
        output_dir=output,
        strict_real_data=True,
    )
    rows = projection["projections"]

    assert set(rows["rating_status"]) == {"both_ratings_available"}
    assert rows["team_a_xg_final"].iloc[0] != rows["team_b_xg_final"].iloc[0]
    assert rows["team_a_win_prob"].iloc[0] != rows["team_b_win_prob"].iloc[0]
