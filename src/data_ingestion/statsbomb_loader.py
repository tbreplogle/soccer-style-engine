from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import STATSBOMB_DEFAULT_ROOT


class StatsBombLoader:
    """Load StatsBomb Open Data from a local clone or extracted folder.

    Runtime network access is intentionally not used. Schemas vary across
    competitions, so tabular returns keep the raw JSON in DataFrame attrs for
    auditing and fallback processing.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else STATSBOMB_DEFAULT_ROOT

    def _read_json(self, relative_path: str | Path) -> list[dict[str, Any]] | dict[str, Any]:
        path = self.root / relative_path
        if not path.exists():
            raise FileNotFoundError(f"StatsBomb file not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _to_frame(raw: list[dict[str, Any]] | dict[str, Any]) -> pd.DataFrame:
        rows = raw if isinstance(raw, list) else [raw]
        df = pd.json_normalize(rows, sep=".")
        df.attrs["raw_json"] = raw
        return df

    def list_competitions(self) -> pd.DataFrame:
        return self._to_frame(self._read_json("competitions.json"))

    def list_matches(self, competition_id: int | str, season_id: int | str) -> pd.DataFrame:
        return self._to_frame(self._read_json(Path("matches") / str(competition_id) / f"{season_id}.json"))

    def load_events(self, match_id: int | str) -> pd.DataFrame:
        return self._to_frame(self._read_json(Path("events") / f"{match_id}.json"))

    def load_lineups(self, match_id: int | str) -> pd.DataFrame:
        return self._to_frame(self._read_json(Path("lineups") / f"{match_id}.json"))

    def load_360(self, match_id: int | str) -> pd.DataFrame:
        return self._to_frame(self._read_json(Path("three-sixty") / f"{match_id}.json"))

    def match_has_360(self, match_id: int | str) -> bool:
        return (self.root / "three-sixty" / f"{match_id}.json").exists()
