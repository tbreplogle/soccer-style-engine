from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
SAMPLE_DATA_DIR = DATA_DIR / "sample"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
REPORTS_DIR = OUTPUTS_DIR / "reports"
PROJECTIONS_DIR = OUTPUTS_DIR / "projections"

STATSBOMB_DEFAULT_ROOT = RAW_DATA_DIR / "statsbomb-open-data"
TEAM_MATCH_STYLE_LOG_PATH = PROCESSED_DATA_DIR / "team_match_style_log.csv"
TEAM_STYLE_PROFILES_PATH = PROCESSED_DATA_DIR / "team_style_profiles.csv"
MATCH_RESULTS_PATH = PROCESSED_DATA_DIR / "match_results.csv"


def ensure_project_dirs() -> None:
    for path in [
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        SAMPLE_DATA_DIR,
        REPORTS_DIR,
        PROJECTIONS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
