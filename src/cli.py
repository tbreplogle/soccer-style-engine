from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.agents.free_proxy_matchup_agent import analyze_free_proxy_matchup
from src.agents.matchup_intelligence_agent import analyze_matchup
from src.agents.team_identity_agent import classify_team_identity
from src.config import TEAM_MATCH_STYLE_LOG_PATH, TEAM_STYLE_PROFILES_PATH, ensure_project_dirs
from src.data_ingestion.football_data_current import normalize_current_inputs
from src.data_ingestion.international_data import build_international_match_dataset, list_international_competitions
from src.data_ingestion.multi_league_football_data import (
    download_football_data_leagues,
    download_football_data_seasons,
    normalize_multi_league_football_data,
    normalize_multi_season_football_data,
)
from src.data_ingestion.statsbomb_loader import StatsBombLoader
from src.features.event_features import build_team_match_style_log
from src.features.free_style_proxies import build_free_style_proxies
from src.features.team_aggregates import build_all_team_style_profiles, build_team_style_profile
from src.models.backtest import run_backtest
from src.models.baseline_diagnostics import run_baseline_diagnostics
from src.models.current_backtest import run_current_backtest
from src.models.confidence_hardening import run_confidence_hardening
from src.models.holdout_validation import run_holdout_validation
from src.models.current_score_projection import project_current_match
from src.models.international_backtest import run_international_backtest
from src.models.international_validation import run_international_validation
from src.models.international_projection import project_international_match
from src.models.international_readiness import audit_international_readiness
from src.models.leakage_audit import run_leakage_audit
from src.models.multi_league_diagnostics import run_multi_league_profile_diagnostics
from src.models.multi_season_validation import run_multi_season_validation
from src.models.projection_profile_diagnostics import run_projection_profile_diagnostics
from src.models.proxy_diagnostics import run_proxy_diagnostics
from src.models.score_projection import project_match
from src.operational.daily_runner import run_daily_pipeline
from src.operational.defaults import explain_operational_defaults
from src.operational.health_check import format_health_check, run_operational_health_check
from src.reports.real_data_validation import run_real_data_validation
from src.reports.projection_report import compare_club_projection_profiles, compare_international_projection_profiles
from src.reports.slate_report import build_club_slate_report, build_international_slate_report


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Soccer style engine Phase 4 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build-style-log")
    p.add_argument("--statsbomb-root", default="data/raw/statsbomb-open-data")
    p.add_argument("--competition-id")
    p.add_argument("--season-id")
    p.add_argument("--output", default=str(TEAM_MATCH_STYLE_LOG_PATH))

    p = sub.add_parser("build-profiles")
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--style-log", default=str(TEAM_MATCH_STYLE_LOG_PATH))
    p.add_argument("--output", default=str(TEAM_STYLE_PROFILES_PATH))

    p = sub.add_parser("identity")
    p.add_argument("--team", required=True)
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--style-log", default=str(TEAM_MATCH_STYLE_LOG_PATH))

    p = sub.add_parser("matchup")
    p.add_argument("--home", required=True)
    p.add_argument("--away", required=True)
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--style-log", default=str(TEAM_MATCH_STYLE_LOG_PATH))

    p = sub.add_parser("project")
    p.add_argument("--home", required=True)
    p.add_argument("--away", required=True)
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--style-log", default=str(TEAM_MATCH_STYLE_LOG_PATH))

    p = sub.add_parser("backtest")
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--style-log", default=str(TEAM_MATCH_STYLE_LOG_PATH))

    p = sub.add_parser("validate-real-data")
    p.add_argument("--statsbomb-root", default="data/raw/statsbomb-open-data")
    p.add_argument("--competition-id")
    p.add_argument("--season-id")
    p.add_argument("--max-matches", type=int, default=10)
    p.add_argument("--output-dir", default="outputs/reports")

    p = sub.add_parser("normalize-football-data")
    p.add_argument("--input")
    p.add_argument("--csv-url")
    p.add_argument("--output", required=True)
    p.add_argument("--league", default="")
    p.add_argument("--season", default="")

    p = sub.add_parser("download-football-data-leagues")
    p.add_argument("--season-code", default="2526")
    p.add_argument("--fallback-season-code", default="2425")
    p.add_argument("--leagues", default="E0,E1,SP1,D1,I1,F1")
    p.add_argument("--output-dir", default="data/raw/football-data")

    p = sub.add_parser("normalize-multi-league-football-data")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--season", default="")

    p = sub.add_parser("download-football-data-seasons")
    p.add_argument("--season-codes", default="2526,2425,2324,2223,2122")
    p.add_argument("--leagues", default="E0,E1,SP1,D1,I1,F1")
    p.add_argument("--output-dir", default="data/raw/football-data")

    p = sub.add_parser("normalize-multi-season-football-data")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)

    p = sub.add_parser("build-free-proxies")
    p.add_argument("--input", required=True)
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--output", default="data/processed/free_style_proxies.csv")

    p = sub.add_parser("project-current")
    p.add_argument("--input", required=True)
    p.add_argument("--home", required=True)
    p.add_argument("--away", required=True)
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--league")
    p.add_argument("--neutral-site", action="store_true")
    p.add_argument("--output", default="outputs/projections/current_match_projection.csv")
    p.add_argument("--enable-proxy-adjustments", action="store_true")
    p.add_argument("--proxy-cap", type=float)
    p.add_argument("--baseline-mode", choices=["goals", "shots", "market", "totals_market", "blended"])
    p.add_argument("--projection-profile", choices=["score_projection", "winner_probability", "total_goals", "market_anchored", "model_only"], default="score_projection")

    p = sub.add_parser("backtest-current")
    p.add_argument("--input", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--output-dir", default="outputs/reports")

    p = sub.add_parser("diagnose-proxies")
    p.add_argument("--input", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--output-dir", default="outputs/reports")
    p.add_argument("--caps", default="0,0.03,0.05,0.08,0.12,0.20")
    p.add_argument("--min-matches", type=int, default=6)
    p.add_argument("--include-window-breakdowns", action="store_true")

    p = sub.add_parser("diagnose-baselines")
    p.add_argument("--input", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--output-dir", default="outputs/reports")
    p.add_argument("--min-matches", type=int, default=6)
    p.add_argument("--monthly", action="store_true")
    p.add_argument("--baseline-modes", default="goals,shots,market,totals_market,blended")
    p.add_argument("--league")

    p = sub.add_parser("diagnose-projection-profiles")
    p.add_argument("--input", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--output-dir", default="outputs/reports")
    p.add_argument("--min-matches", type=int, default=6)
    p.add_argument("--profiles", default="score_projection,winner_probability,total_goals,market_anchored,model_only")

    p = sub.add_parser("diagnose-multi-league-profiles")
    p.add_argument("--input", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--output-dir", default="outputs/reports")
    p.add_argument("--profiles", default="score_projection,winner_probability,total_goals,market_anchored,model_only")
    p.add_argument("--min-matches", type=int, default=6)
    p.add_argument("--monthly", action="store_true")

    p = sub.add_parser("validate-multi-season-profiles")
    p.add_argument("--input", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--output-dir", default="outputs/reports")
    p.add_argument("--profiles", default="score_projection,winner_probability,total_goals,market_anchored,model_only")
    p.add_argument("--min-matches", type=int, default=6)
    p.add_argument("--monthly", action="store_true")
    p.add_argument("--by-league", action="store_true")
    p.add_argument("--by-season", action="store_true")

    p = sub.add_parser("run-holdout-validation")
    p.add_argument("--input", required=True)
    p.add_argument("--train-seasons", required=True)
    p.add_argument("--validation-season", required=True)
    p.add_argument("--test-season", required=True)
    p.add_argument("--output-dir", default="outputs/reports")

    p = sub.add_parser("harden-confidence")
    p.add_argument("--input", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--output-dir", default="outputs/reports")

    p = sub.add_parser("audit-leakage")
    p.add_argument("--input", required=True)
    p.add_argument("--start-date")
    p.add_argument("--end-date")
    p.add_argument("--output-dir", default="outputs/reports")

    p = sub.add_parser("validate-international")
    p.add_argument("--statsbomb-root", default="data/raw/statsbomb-open-data/data")
    p.add_argument("--competition-name")
    p.add_argument("--season-id")
    p.add_argument("--max-matches", type=int, default=64)
    p.add_argument("--output-dir", default="outputs/reports")

    p = sub.add_parser("audit-international-readiness")
    p.add_argument("--statsbomb-root", default="data/raw/statsbomb-open-data/data")
    p.add_argument("--output-dir", default="outputs/reports")

    p = sub.add_parser("list-international-competitions")
    p.add_argument("--statsbomb-root", default="data/raw/statsbomb-open-data/data")

    p = sub.add_parser("build-international-dataset")
    p.add_argument("--statsbomb-root", default="data/raw/statsbomb-open-data/data")
    p.add_argument("--output", default="data/processed/international_match_results.csv")
    p.add_argument("--competition-name")
    p.add_argument("--competition-id")
    p.add_argument("--season-id")
    p.add_argument("--max-matches", type=int)

    p = sub.add_parser("project-international")
    p.add_argument("--input", required=True)
    p.add_argument("--team-a", required=True)
    p.add_argument("--team-b", required=True)
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--neutral-site", choices=["true", "false", "unknown"], default="unknown")
    p.add_argument("--projection-profile", choices=["international_score_projection", "international_winner_probability", "international_total_goals", "international_event_style_context", "international_model_only"], default="international_score_projection")
    p.add_argument("--competition-context", default="")
    p.add_argument("--output", default="outputs/projections/international_match_projection.csv")

    p = sub.add_parser("backtest-international")
    p.add_argument("--input", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--competition-name")
    p.add_argument("--competition-id")
    p.add_argument("--season-id")
    p.add_argument("--output-dir", default="outputs/reports")
    p.add_argument("--min-prior-matches", type=int, default=5)

    p = sub.add_parser("build-club-slate")
    p.add_argument("--input", required=True)
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--league")
    p.add_argument("--output-dir", default="outputs/reports")
    p.add_argument("--projection-output-dir", default="outputs/projections")
    p.add_argument("--profiles", default="score_projection,winner_probability,total_goals,market_anchored,model_only")
    p.add_argument("--slate-type", choices=["auto", "future", "historical"], default="auto")
    p.add_argument("--max-matches", type=int, default=20)
    p.add_argument("--matchups-csv")

    p = sub.add_parser("compare-club-profiles")
    p.add_argument("--input", required=True)
    p.add_argument("--home", required=True)
    p.add_argument("--away", required=True)
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--league")
    p.add_argument("--profiles", default="score_projection,winner_probability,total_goals,market_anchored,model_only")
    p.add_argument("--output-dir", default="outputs/reports")
    p.add_argument("--projection-output-dir", default="outputs/projections")

    p = sub.add_parser("build-international-slate")
    p.add_argument("--input", required=True)
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--team-a")
    p.add_argument("--team-b")
    p.add_argument("--matchups-csv")
    p.add_argument("--neutral-site", choices=["true", "false", "unknown"], default="unknown")
    p.add_argument("--competition-context", default="")
    p.add_argument("--profiles", default="international_score_projection,international_winner_probability,international_total_goals,international_event_style_context,international_model_only")
    p.add_argument("--max-matches", type=int, default=20)
    p.add_argument("--output-dir", default="outputs/reports")
    p.add_argument("--projection-output-dir", default="outputs/projections")

    p = sub.add_parser("compare-international-profiles")
    p.add_argument("--input", required=True)
    p.add_argument("--team-a", required=True)
    p.add_argument("--team-b", required=True)
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--neutral-site", choices=["true", "false", "unknown"], default="unknown")
    p.add_argument("--competition-context", default="")
    p.add_argument("--profiles", default="international_score_projection,international_winner_probability,international_total_goals,international_event_style_context,international_model_only")
    p.add_argument("--output-dir", default="outputs/reports")
    p.add_argument("--projection-output-dir", default="outputs/projections")

    p = sub.add_parser("run-daily-pipeline")
    p.add_argument("--as-of-date", required=True)
    p.add_argument("--season-code", default="2526")
    p.add_argument("--fallback-season-code", default="2425")
    p.add_argument("--leagues", default="E0,E1,SP1,D1,I1,F1")
    p.add_argument("--output-root", default="outputs/runs")
    p.add_argument("--slate-type", choices=["auto", "future", "historical", "manual"], default="auto")
    p.add_argument("--max-matches", type=int, default=20)
    p.add_argument("--manual-club-matchups")
    p.add_argument("--include-international", action="store_true")
    p.add_argument("--international-input")
    p.add_argument("--manual-international-matchups")
    p.add_argument("--skip-download", action="store_true")
    p.add_argument("--run-quick-audit", action="store_true")
    p.add_argument("--raw-input-dir", default="data/raw/football-data")
    p.add_argument("--processed-output", default="data/processed/operational_current_match_results.csv")

    sub.add_parser("explain-operational-defaults")
    sub.add_parser("operational-health-check")

    return parser


def main(argv: list[str] | None = None) -> None:
    ensure_project_dirs()
    args = build_parser().parse_args(argv)
    if args.command == "build-style-log":
        loader = StatsBombLoader(args.statsbomb_root)
        if args.competition_id and args.season_id:
            matches = loader.list_matches(args.competition_id, args.season_id)
        else:
            sample_matches = Path("data/sample/statsbomb-open-data/matches/1/1.json")
            if sample_matches.exists():
                loader = StatsBombLoader("data/sample/statsbomb-open-data")
                matches = loader.list_matches(1, 1)
            else:
                raise ValueError("Provide --competition-id and --season-id or add sample StatsBomb files.")
        result = build_team_match_style_log(matches, loader, output_path=args.output)
        print(f"Wrote {len(result)} team-match rows to {args.output}")
    elif args.command == "build-profiles":
        result = build_all_team_style_profiles(args.as_of_date, style_log=args.style_log, output_path=args.output)
        print(f"Wrote {len(result)} profiles to {args.output}")
    elif args.command == "identity":
        profile = build_team_style_profile(args.team, args.as_of_date, style_log=args.style_log)
        _print_json(classify_team_identity(profile))
    elif args.command == "matchup":
        _print_json(analyze_matchup(args.home, args.away, args.as_of_date, style_log=args.style_log))
    elif args.command == "project":
        projection = project_match(args.home, args.away, args.as_of_date, style_log=args.style_log)
        print(projection.to_string(index=False))
    elif args.command == "backtest":
        result = run_backtest(args.start_date, args.end_date, style_log=args.style_log)
        print(result["summary"])
    elif args.command == "validate-real-data":
        result = run_real_data_validation(
            args.statsbomb_root,
            competition_id=args.competition_id,
            season_id=args.season_id,
            max_matches=args.max_matches,
            output_dir=args.output_dir,
        )
        quality = result["quality"].to_dict("records")
        print(
            "Real data validation complete: "
            f"matches={len(result['matches'])}, "
            f"team_match_rows={len(result['style_log'])}, "
            f"quality_flags={quality}, "
            f"warnings={len(result['sanity_warnings'])}, "
            f"report={result['report_path']}"
        )
    elif args.command == "normalize-football-data":
        result = normalize_current_inputs(
            input_path=args.input,
            csv_url=args.csv_url,
            output_path=args.output,
            league=args.league,
            season=args.season,
        )
        print(f"Wrote {len(result)} normalized current rows to {args.output}")
    elif args.command == "download-football-data-leagues":
        leagues = [league for league in args.leagues.split(",") if league.strip()]
        result = download_football_data_leagues(
            season_code=args.season_code,
            leagues=leagues,
            fallback_season_code=args.fallback_season_code,
            output_dir=args.output_dir,
        )
        print(result.to_string(index=False))
    elif args.command == "normalize-multi-league-football-data":
        result = normalize_multi_league_football_data(args.input, output_path=args.output, season=args.season)
        print(f"Wrote {len(result)} normalized multi-league current rows to {args.output}")
    elif args.command == "download-football-data-seasons":
        season_codes = [code.strip() for code in args.season_codes.split(",") if code.strip()]
        leagues = [league.strip() for league in args.leagues.split(",") if league.strip()]
        result = download_football_data_seasons(
            season_codes=season_codes,
            leagues=leagues,
            output_dir=args.output_dir,
        )
        print(result.to_string(index=False))
    elif args.command == "normalize-multi-season-football-data":
        result = normalize_multi_season_football_data(args.input, output_path=args.output)
        print(f"Wrote {len(result)} normalized multi-season rows to {args.output}")
    elif args.command == "build-free-proxies":
        result = build_free_style_proxies(args.input, args.as_of_date)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
        print(f"Wrote {len(result)} free proxy rows to {args.output}")
    elif args.command == "project-current":
        result = project_current_match(
            args.input,
            args.home,
            args.away,
            args.as_of_date,
            league=args.league,
            neutral_site=args.neutral_site,
            output_path=args.output,
            enable_proxy_adjustments=args.enable_proxy_adjustments,
            proxy_total_cap=args.proxy_cap,
            baseline_mode=args.baseline_mode,
            projection_profile=args.projection_profile,
        )
        print(result.to_string(index=False))
    elif args.command == "backtest-current":
        result = run_current_backtest(
            args.input,
            args.start_date,
            args.end_date,
            output_dir=args.output_dir,
        )
        print(result["summary"])
    elif args.command == "diagnose-proxies":
        caps = [float(x) for x in args.caps.split(",") if x.strip()]
        result = run_proxy_diagnostics(
            args.input,
            args.start_date,
            args.end_date,
            caps=caps,
            min_matches=args.min_matches,
            output_dir=args.output_dir,
            include_breakdowns=args.include_window_breakdowns,
        )
        print(result["report"])
    elif args.command == "diagnose-projection-profiles":
        profiles = [profile for profile in args.profiles.split(",") if profile.strip()]
        result = run_projection_profile_diagnostics(
            args.input,
            args.start_date,
            args.end_date,
            profiles=profiles,
            min_matches=args.min_matches,
            output_dir=args.output_dir,
        )
        print(result["report"])
    elif args.command == "diagnose-multi-league-profiles":
        profiles = [profile for profile in args.profiles.split(",") if profile.strip()]
        result = run_multi_league_profile_diagnostics(
            args.input,
            args.start_date,
            args.end_date,
            profiles=profiles,
            min_matches=args.min_matches,
            monthly=args.monthly,
            output_dir=args.output_dir,
        )
        print(result["report"])
    elif args.command == "validate-multi-season-profiles":
        profiles = [profile.strip() for profile in args.profiles.split(",") if profile.strip()]
        result = run_multi_season_validation(
            args.input,
            args.start_date,
            args.end_date,
            profiles=profiles,
            min_matches=args.min_matches,
            monthly=args.monthly,
            by_league=args.by_league,
            by_season=args.by_season,
            output_dir=args.output_dir,
        )
        print(result["report"])
    elif args.command == "run-holdout-validation":
        result = run_holdout_validation(
            args.input,
            train_seasons=args.train_seasons,
            validation_season=args.validation_season,
            test_season=args.test_season,
            output_dir=args.output_dir,
        )
        print(result["report"])
    elif args.command == "harden-confidence":
        result = run_confidence_hardening(
            args.input,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
        print(result["report"])
    elif args.command == "audit-leakage":
        result = run_leakage_audit(
            args.input,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
        print(result["report"])
    elif args.command == "validate-international":
        result = run_international_validation(
            statsbomb_root=args.statsbomb_root,
            competition_name=args.competition_name,
            season_id=args.season_id,
            max_matches=args.max_matches,
            output_dir=args.output_dir,
        )
        print(result["report"])
    elif args.command == "audit-international-readiness":
        result = audit_international_readiness(args.statsbomb_root, output_dir=args.output_dir)
        print(result["report"])
    elif args.command == "list-international-competitions":
        result = list_international_competitions(args.statsbomb_root)
        print(result.to_string(index=False))
    elif args.command == "build-international-dataset":
        result = build_international_match_dataset(
            statsbomb_root=args.statsbomb_root,
            output_path=args.output,
            competition_name=args.competition_name,
            competition_id=args.competition_id,
            season_id=args.season_id,
            max_matches=args.max_matches,
        )
        print(f"Wrote {len(result)} international match rows to {args.output}")
    elif args.command == "project-international":
        result = project_international_match(
            args.input,
            args.team_a,
            args.team_b,
            args.as_of_date,
            neutral_site=args.neutral_site,
            projection_profile=args.projection_profile,
            competition_context=args.competition_context,
            output_path=args.output,
        )
        print(result.to_string(index=False))
    elif args.command == "backtest-international":
        result = run_international_backtest(
            args.input,
            args.start_date,
            args.end_date,
            competition_name=args.competition_name,
            competition_id=args.competition_id,
            season_id=args.season_id,
            output_dir=args.output_dir,
            min_prior_matches=args.min_prior_matches,
        )
        print(result["summary"])
    elif args.command == "build-club-slate":
        result = build_club_slate_report(
            args.input,
            args.as_of_date,
            league=args.league,
            projection_profiles=args.profiles,
            output_dir=args.output_dir,
            projection_output_dir=args.projection_output_dir,
            slate_type=args.slate_type,
            max_matches=args.max_matches,
            matchups_csv=args.matchups_csv,
        )
        print(f"Wrote {len(result['results'])} club slate projection rows to {result['csv_path']}")
        print(f"Wrote club slate report to {result['markdown_path']}")
    elif args.command == "compare-club-profiles":
        result = compare_club_projection_profiles(
            args.input,
            args.home,
            args.away,
            args.as_of_date,
            profiles=args.profiles,
            output_dir=args.output_dir,
            projection_output_dir=args.projection_output_dir,
            league=args.league,
        )
        print(result["results"].to_string(index=False))
    elif args.command == "build-international-slate":
        result = build_international_slate_report(
            args.input,
            args.as_of_date,
            neutral_site=args.neutral_site,
            projection_profiles=args.profiles,
            output_dir=args.output_dir,
            projection_output_dir=args.projection_output_dir,
            team_a=args.team_a,
            team_b=args.team_b,
            competition_context=args.competition_context,
            matchups_csv=args.matchups_csv,
            max_matches=args.max_matches,
        )
        print(f"Wrote {len(result['results'])} international slate projection rows to {result['csv_path']}")
        print(f"Wrote international slate report to {result['markdown_path']}")
    elif args.command == "compare-international-profiles":
        result = compare_international_projection_profiles(
            args.input,
            args.team_a,
            args.team_b,
            args.as_of_date,
            neutral_site=args.neutral_site,
            competition_context=args.competition_context,
            profiles=args.profiles,
            output_dir=args.output_dir,
            projection_output_dir=args.projection_output_dir,
        )
        print(result["results"].to_string(index=False))
    elif args.command == "run-daily-pipeline":
        result = run_daily_pipeline(
            as_of_date=args.as_of_date,
            season_code=args.season_code,
            fallback_season_code=args.fallback_season_code,
            leagues=args.leagues,
            output_root=args.output_root,
            slate_type=args.slate_type,
            max_matches=args.max_matches,
            include_international=args.include_international,
            international_input=args.international_input,
            manual_club_matchups=args.manual_club_matchups,
            manual_international_matchups=args.manual_international_matchups,
            skip_download=args.skip_download,
            run_quick_audit=args.run_quick_audit,
            raw_input_dir=args.raw_input_dir,
            processed_output=args.processed_output,
        )
        print(f"Daily pipeline complete: run_dir={result['run_dir']}")
        print(f"Manifest: {result['manifest_path']}")
        print(f"Summary: {result['summary_path']}")
        if result["warnings"]:
            print("Warnings:")
            for warning in result["warnings"]:
                print(f"- {warning}")
    elif args.command == "explain-operational-defaults":
        print(explain_operational_defaults())
    elif args.command == "operational-health-check":
        print(format_health_check(run_operational_health_check()))
    elif args.command == "diagnose-baselines":
        modes = [m for m in args.baseline_modes.split(",") if m.strip()]
        result = run_baseline_diagnostics(
            args.input,
            args.start_date,
            args.end_date,
            baseline_modes=modes,
            min_matches=args.min_matches,
            monthly=args.monthly,
            output_dir=args.output_dir,
            league=args.league,
        )
        print(result["report"])


if __name__ == "__main__":
    main()
