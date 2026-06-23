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
from src.data_ingestion.statsbomb_loader import StatsBombLoader
from src.features.event_features import build_team_match_style_log
from src.features.free_style_proxies import build_free_style_proxies
from src.features.team_aggregates import build_all_team_style_profiles, build_team_style_profile
from src.models.backtest import run_backtest
from src.models.current_backtest import run_current_backtest
from src.models.current_score_projection import project_current_match
from src.models.score_projection import project_match
from src.reports.real_data_validation import run_real_data_validation


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

    p = sub.add_parser("backtest-current")
    p.add_argument("--input", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--output-dir", default="outputs/reports")

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


if __name__ == "__main__":
    main()
