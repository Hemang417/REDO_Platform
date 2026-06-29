"""
Individual scoring rule functions.

Each function accepts the relevant CleanProject fields and the relevant
config section, and returns a float in [0.0, 1.0].

Single responsibility: one pure function per scoring factor.
No I/O, no logging, no side effects.
"""

from __future__ import annotations

from typing import Optional

from src.config.loader import (
    ConstructionProgressConfig,
    DelayConfig,
    ExtensionConfig,
    LocationConfig,
    ViabilityConfig,
)


def score_construction_progress(
    progress: Optional[float],
    cfg: ConstructionProgressConfig,
) -> float:
    """Score based on how far along construction is.

    Sweet spot is cfg.optimal_min – cfg.optimal_max %.
    Completed projects score low (no capital need).
    """
    if progress is None:
        return 0.5  # unknown — neutral

    if progress >= 100.0:
        return cfg.score_complete
    if cfg.optimal_min <= progress <= cfg.optimal_max:
        return cfg.score_in_optimal
    if progress > cfg.optimal_max:
        return cfg.score_above_optimal
    return cfg.score_below_optimal


def score_delay_severity(
    delay_days: Optional[int],
    cfg: DelayConfig,
) -> float:
    """Score based on how overdue the project is.

    No delay = low score (on-time projects rarely need AIF capital).
    Moderate delay = high score (classic funding gap).
    Extreme delay = low score (likely unrecoverable).
    """
    if delay_days is None:
        return 0.5  # unknown — neutral

    if delay_days <= 0:
        return cfg.no_delay_score

    if cfg.moderate_delay_min_days <= delay_days <= cfg.moderate_delay_max_days:
        return cfg.moderate_delay_score

    if delay_days <= cfg.severe_delay_max_days:
        return cfg.severe_delay_score

    return cfg.extreme_delay_score


def score_extension_history(
    extension_count: int,
    cfg: ExtensionConfig,
) -> float:
    """Score based on how many RERA extensions the developer has taken.

    1–2 extensions: developer used the regulatory mechanism — funding gap signal.
    3+: repeatedly troubled project.
    """
    scores_dict = dict(cfg.scores)

    if extension_count >= 4:
        return cfg.four_plus_score

    return scores_dict.get(extension_count, cfg.four_plus_score)


def score_project_viability(
    current_status: Optional[str],
    is_lapsed: Optional[bool],
    is_deregistered: Optional[bool],
    is_abeyance: Optional[bool],
    cfg: ViabilityConfig,
) -> float:
    """Score based on legal/regulatory status.

    Lapsed or deregistered projects are hard zeros — legal standing is a
    prerequisite for any investment.
    """
    # Hard gates first
    if is_lapsed is True:
        return cfg.lapsed_score
    if is_deregistered is True:
        return cfg.deregistered_score
    if is_abeyance is True:
        return cfg.abeyance_score

    # Derive from current_status string
    if current_status is None:
        return cfg.unknown_score

    status_lower = current_status.lower()
    if "complet" in status_lower:
        return cfg.completed_score
    if "laps" in status_lower:
        return cfg.lapsed_score
    if "deregist" in status_lower:
        return cfg.deregistered_score
    if "abeyance" in status_lower:
        return cfg.abeyance_score
    if "active" in status_lower or "ongoing" in status_lower or "new" in status_lower:
        return cfg.active_score

    return cfg.unknown_score


def score_location(
    district: str,
    cfg: LocationConfig,
) -> tuple[float, str]:
    """Score based on district tier.

    Returns (score, tier_label) so the caller can store both.
    """
    normalised = district.strip().title()

    if normalised in cfg.tier1_districts:
        return cfg.tier1_score, "tier1"
    if normalised in cfg.tier2_districts:
        return cfg.tier2_score, "tier2"
    return cfg.other_score, "other"
