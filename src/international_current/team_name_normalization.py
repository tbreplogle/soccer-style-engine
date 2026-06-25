from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


ALIASES = {
    "usa": "United States",
    "u.s.a.": "United States",
    "united states": "United States",
    "usmnt": "United States",
    "us": "United States",
    "south korea": "South Korea",
    "korea republic": "South Korea",
    "republic of korea": "South Korea",
    "ivory coast": "Cote d'Ivoire",
    "cote d'ivoire": "Cote d'Ivoire",
    "côte d'ivoire": "Cote d'Ivoire",
    "cote divoire": "Cote d'Ivoire",
    "dr congo": "Congo DR",
    "congo dr": "Congo DR",
    "democratic republic of congo": "Congo DR",
    "curacao": "Curacao",
    "cura\u00e7ao": "Curacao",
    "curaçao": "Curacao",
    "czechia": "Czech Republic",
    "czech republic": "Czech Republic",
    "bosnia and herzegovina": "Bosnia and Herzegovina",
    "bosnia & herzegovina": "Bosnia and Herzegovina",
    "bosnia/herzegovina": "Bosnia and Herzegovina",
    "bosnia herzegovina": "Bosnia and Herzegovina",
    "bosnia-herzegovina": "Bosnia and Herzegovina",
    "bosnia": "Bosnia and Herzegovina",
    "curaçao": "Curacao",
    "turkiye": "Turkiye",
    "t\u00fcrkiye": "Turkiye",
    "tã¼rkiye": "Turkiye",
    "turkey": "Turkiye",
    "iran": "Iran",
    "ir iran": "Iran",
    "netherlands": "Netherlands",
    "holland": "Netherlands",
    "england men": "England",
    "germany men": "Germany",
    "japan men": "Japan",
    "australia men": "Australia",
    "sweden men": "Sweden",
    "tunisia men": "Tunisia",
    "paraguay men": "Paraguay",
    "ecuador men": "Ecuador",
    "scotland men": "Scotland",
    "wales men": "Wales",
    "republic of ireland": "Ireland",
    "ireland": "Ireland",
    "china pr": "China",
    "china": "China",
    "saudi arabia men": "Saudi Arabia",
    "new zealand men": "New Zealand",
}


@dataclass(frozen=True)
class NormalizedTeamName:
    raw_name: str
    normalized_name: str
    warning: str = ""


def _key(name: str) -> str:
    return " ".join(str(name or "").strip().lower().replace("-", " ").split())


def normalize_team_name(name: str, known_names: Iterable[str] | None = None) -> NormalizedTeamName:
    raw = str(name or "").strip()
    if not raw:
        return NormalizedTeamName(raw, "", "Missing team name.")
    normalized = ALIASES.get(_key(raw), raw)
    if known_names:
        known = {str(item).strip() for item in known_names if str(item).strip()}
        if normalized not in known:
            return NormalizedTeamName(raw, normalized, f"Unknown normalized team name: {normalized}")
    return NormalizedTeamName(raw, normalized, "" if normalized == raw else f"Normalized {raw} to {normalized}.")


def normalize_team_pair(home: str, away: str, known_names: Iterable[str] | None = None) -> tuple[str, str, list[str]]:
    home_norm = normalize_team_name(home, known_names)
    away_norm = normalize_team_name(away, known_names)
    warnings = [item.warning for item in [home_norm, away_norm] if item.warning]
    return home_norm.normalized_name, away_norm.normalized_name, warnings
