"""
Aggregates ScoredProject records by developer to build DeveloperProfile objects.

Grouping key priority:
  1. promoter_profile_id (numeric, authoritative MAHARERA ID)
  2. developer_name (fallback when profile_id is None)

Single responsibility: grouping + metric computation.
No I/O, no HTTP, no business rules beyond what's in config.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from statistics import mean
from typing import Optional

from src.config.loader import DeveloperScoringConfig
from src.models.developer_profile import DeveloperProfile
from src.models.scored_project import ScoredProject

logger = logging.getLogger(__name__)


def _linear_interpolate(
    value: float,
    poor: float,
    excellent: float,
    reverse: bool = False,
) -> float:
    """Map value linearly to [0.0, 1.0] between poor and excellent thresholds.

    Args:
        reverse: If True, lower value is better (e.g. lapse rate).
    """
    if excellent == poor:
        return 1.0
    if not reverse:
        clamped = max(poor, min(excellent, value))
        return (clamped - poor) / (excellent - poor)
    else:
        clamped = max(excellent, min(poor, value))
        return (poor - clamped) / (poor - excellent)


def _score_portfolio_size(count: int, cfg) -> float:
    if count <= cfg.small_threshold:
        return cfg.single_score
    if count >= cfg.large_threshold:
        return 1.0
    return _linear_interpolate(
        count,
        poor=float(cfg.small_threshold),
        excellent=float(cfg.large_threshold),
    )


class DeveloperAggregator:
    """Groups ScoredProjects by developer and computes DeveloperProfile objects."""

    def __init__(self, config: DeveloperScoringConfig) -> None:
        self._cfg = config

    def aggregate(
        self, projects: list[ScoredProject]
    ) -> list[DeveloperProfile]:
        """Group projects by developer and compute a profile for each.

        Returns list of DeveloperProfile sorted by track_record_score descending.
        """
        groups = self._group(projects)
        profiles = [self._build_profile(name, pid, bucket) for (name, pid), bucket in groups.items()]
        profiles.sort(key=lambda p: p.track_record_score, reverse=True)
        logger.info(
            "Aggregated %d projects into %d developer profiles",
            len(projects),
            len(profiles),
        )
        return profiles

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------

    def _group(
        self, projects: list[ScoredProject]
    ) -> dict[tuple, list[ScoredProject]]:
        """Group projects. Key = (canonical_name, profile_id_or_None)."""
        groups: dict[tuple, list[ScoredProject]] = defaultdict(list)
        for p in projects:
            key = (p.developer_name, p.promoter_profile_id)
            groups[key].append(p)
        return dict(groups)

    # ------------------------------------------------------------------
    # Profile construction
    # ------------------------------------------------------------------

    def _build_profile(
        self,
        developer_name: str,
        promoter_profile_id: Optional[int],
        projects: list[ScoredProject],
    ) -> DeveloperProfile:
        total = len(projects)

        # Status counts
        completed = sum(1 for p in projects if (p.current_status or "").lower().startswith("complet"))
        lapsed = sum(1 for p in projects if p.is_lapsed is True or (p.current_status or "").lower().startswith("laps"))
        deregistered = sum(1 for p in projects if p.is_deregistered is True)
        abeyance = sum(1 for p in projects if p.is_abeyance is True)
        active = total - completed - lapsed - deregistered - abeyance

        # Delivery metrics
        with_delay = [p for p in projects if p.delay_days is not None]
        on_time = [p for p in with_delay if p.delay_days is not None and p.delay_days <= 0]
        delay_vals = [p.delay_days for p in with_delay if p.delay_days is not None]
        avg_delay = round(mean(delay_vals), 1) if delay_vals else None
        max_delay = max(delay_vals) if delay_vals else None
        on_time_rate = round(len(on_time) / len(with_delay), 4) if with_delay else None
        completion_rate = round(completed / total, 4) if total else None
        lapse_rate = round(lapsed / total, 4) if total else None
        avg_ext = round(mean(p.extension_count for p in projects), 2) if projects else None

        # Construction progress (active only)
        progress_vals = [
            p.construction_progress_pct
            for p in projects
            if p.construction_progress_pct is not None
            and not (p.current_status or "").lower().startswith("complet")
        ]
        avg_progress = round(mean(progress_vals), 1) if progress_vals else None

        # Opportunity scores
        opp_vals = [p.opportunity_score for p in projects]
        avg_opp = round(mean(opp_vals), 2) if opp_vals else None
        max_opp = round(max(opp_vals), 2) if opp_vals else None

        # Districts
        district_counter = Counter(p.district for p in projects if p.district)
        districts = sorted(district_counter.keys())
        primary_district = district_counter.most_common(1)[0][0] if district_counter else None

        # Track record score
        track_record_score = self._compute_track_record_score(
            completion_rate=completion_rate,
            on_time_rate=on_time_rate,
            lapse_rate=lapse_rate,
            total_projects=total,
        )

        return DeveloperProfile(
            promoter_profile_id=promoter_profile_id,
            developer_name=developer_name,
            total_projects=total,
            active_projects=max(0, active),
            completed_projects=completed,
            lapsed_projects=lapsed,
            deregistered_projects=deregistered,
            abeyance_projects=abeyance,
            completion_rate=completion_rate,
            on_time_rate=on_time_rate,
            lapse_rate=lapse_rate,
            avg_delay_days=avg_delay,
            max_delay_days=max_delay,
            avg_extensions=avg_ext,
            avg_construction_progress=avg_progress,
            avg_opportunity_score=avg_opp,
            max_opportunity_score=max_opp,
            districts=districts,
            primary_district=primary_district,
            track_record_score=track_record_score,
            project_ids=sorted(p.project_id for p in projects),
        )

    # ------------------------------------------------------------------
    # Track record scoring
    # ------------------------------------------------------------------

    def _compute_track_record_score(
        self,
        completion_rate: Optional[float],
        on_time_rate: Optional[float],
        lapse_rate: Optional[float],
        total_projects: int,
    ) -> float:
        cfg = self._cfg
        w = cfg.weights

        cr_score = _linear_interpolate(
            completion_rate if completion_rate is not None else 0.0,
            poor=cfg.completion_rate.poor_threshold,
            excellent=cfg.completion_rate.excellent_threshold,
        )
        ot_score = _linear_interpolate(
            on_time_rate if on_time_rate is not None else 0.0,
            poor=cfg.on_time_rate.poor_threshold,
            excellent=cfg.on_time_rate.excellent_threshold,
        )
        # no_lapse_rate = 1 - lapse_rate; higher is better
        no_lapse = 1.0 - (lapse_rate if lapse_rate is not None else 0.0)
        nl_score = _linear_interpolate(
            no_lapse,
            poor=cfg.no_lapse_rate.poor_threshold,
            excellent=cfg.no_lapse_rate.excellent_threshold,
        )
        ps_score = _score_portfolio_size(total_projects, cfg.portfolio_size)

        raw = (
            cr_score * w.completion_rate
            + ot_score * w.on_time_rate
            + nl_score * w.no_lapse_rate
            + ps_score * w.portfolio_size
        )
        return round(max(0.0, min(100.0, raw * 100)), 2)
