from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ClubOperationalDefaults:
    general_report_profile: str = "score_projection"
    primary_wdl_profile: str = "winner_probability"
    default_baseline_mode: str = "blended"
    proxy_adjustments_enabled: bool = False
    confidence_language: str = "data_support_context"
    max_default_matches: int = 20
    default_leagues: tuple[str, ...] = ("E0", "E1", "SP1", "D1", "I1", "F1")
    default_current_season_code: str = "2526"
    fallback_season_code: str = "2425"


@dataclass(frozen=True)
class InternationalOperationalDefaults:
    enabled_by_default: bool = False
    run_only_if_data_exists: bool = True
    confidence_language: str = "conservative_context"
    require_historical_or_event_label: bool = True
    do_not_mix_club_ratings: bool = True


@dataclass(frozen=True)
class GuardrailDefaults:
    no_betting_recommendations: bool = True
    blocked_language_categories: tuple[str, ...] = ("wagering_action_language", "selection_advice_language")
    no_current_true_event_style_claim_without_current_event_data: bool = True
    generated_outputs_ignored: bool = True
    proxy_adjustments_disabled_by_default: bool = True


@dataclass(frozen=True)
class OperationalDefaults:
    club: ClubOperationalDefaults = ClubOperationalDefaults()
    international: InternationalOperationalDefaults = InternationalOperationalDefaults()
    guardrails: GuardrailDefaults = GuardrailDefaults()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


OPERATIONAL_DEFAULTS = OperationalDefaults()


def explain_operational_defaults(defaults: OperationalDefaults = OPERATIONAL_DEFAULTS) -> str:
    club = defaults.club
    lines = [
        "Operational Defaults",
        "",
        f"General report profile: {club.general_report_profile}",
        f"Primary W/D/L profile: {club.primary_wdl_profile}",
        f"Default baseline mode: {club.default_baseline_mode}",
        f"Proxy adjustments enabled: {club.proxy_adjustments_enabled}",
        f"Confidence language: {club.confidence_language}",
        f"Default leagues: {','.join(club.default_leagues)}",
        f"Default current season code: {club.default_current_season_code}",
        f"Fallback season code: {club.fallback_season_code}",
        "",
        "Why these defaults:",
        "- Phase 14 multi-season validation found winner_probability strongest for W/D/L context.",
        "- score_projection remains the general report view because it is the clearest xG-style projection surface.",
        "- Confidence remains context-only and is better described as Data Support or Risk Context.",
        "- Proxy score adjustments remain disabled by default; free_proxy_style is not true event/tracking style.",
        "- Market gaps are diagnostic context, not betting recommendations.",
        "",
        "Guardrails:",
        "- No wagering recommendations or action language.",
        "- No current true event-style claim unless current event data exists.",
        "- Club and international ratings stay separate.",
        "- Generated outputs stay in ignored folders.",
        "",
        "Current limitations:",
        "- Totals are less settled than W/D/L and need more validation.",
        "- Confidence labels are not calibrated enough to mean certainty.",
        "- International projections remain optional and conservative.",
        "- UI, PassSonar, heat maps, style fingerprints, dashboards, and event visuals are deferred.",
    ]
    return "\n".join(lines)
