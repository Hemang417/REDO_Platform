"""
Applies all scoring rules to a CleanProject and produces a ScoredProject.

Single responsibility: weighted aggregation only.
All rule logic lives in rules.py; all config lives in scoring_rules.yaml.
"""

from __future__ import annotations

import logging

from src.config.loader import ScoringConfig
from src.models.clean_project import CleanProject
from src.models.scored_project import ScoredProject
from src.scorer.rules import (
    score_construction_progress,
    score_delay_severity,
    score_extension_history,
    score_location,
    score_project_viability,
)

logger = logging.getLogger(__name__)

_FACTOR_NAMES = (
    "construction_progress",
    "delay_severity",
    "extension_history",
    "project_viability",
    "location",
)


class MahareraScorer:
    """Scores CleanProject records using weighted factor rules.

    Inject ScoringConfig so weights and thresholds stay in YAML.
    """

    def __init__(self, config: ScoringConfig) -> None:
        self._cfg = config

    def score(self, project: CleanProject) -> ScoredProject:
        """Apply all rules and return a ScoredProject.

        The opportunity_score is the weighted sum of factor scores × 100,
        clamped to [0, 100].
        """
        cfg = self._cfg
        w = cfg.weights

        # Compute per-factor scores [0.0, 1.0]
        cp_score = score_construction_progress(
            project.construction_progress_pct, cfg.construction_progress
        )
        delay_score = score_delay_severity(
            project.delay_days, cfg.delay_severity
        )
        ext_score = score_extension_history(
            project.extension_count, cfg.extension_history
        )
        viability_score = score_project_viability(
            project.current_status,
            project.is_lapsed,
            project.is_deregistered,
            project.is_abeyance,
            cfg.project_viability,
        )
        location_score, tier = score_location(
            project.district, cfg.location
        )

        factor_scores = {
            "construction_progress": round(cp_score, 4),
            "delay_severity": round(delay_score, 4),
            "extension_history": round(ext_score, 4),
            "project_viability": round(viability_score, 4),
            "location": round(location_score, 4),
        }

        # Viability is a multiplier, not an additive factor.
        # A lapsed/deregistered project (viability=0) scores 0 regardless of
        # other factors — legal standing is a prerequisite for AIF investment.
        # The 4 non-viability factors are normalised to [0,1] among themselves,
        # then scaled by the viability multiplier.
        non_viability_weight = (
            w.construction_progress + w.delay_severity
            + w.extension_history + w.location
        )
        if non_viability_weight > 0:
            non_viability_score = (
                cp_score * w.construction_progress
                + delay_score * w.delay_severity
                + ext_score * w.extension_history
                + location_score * w.location
            ) / non_viability_weight
        else:
            non_viability_score = 0.0

        raw_score = non_viability_score * viability_score
        opportunity_score = round(max(0.0, min(100.0, raw_score * 100)), 2)

        logger.debug(
            "Scored project_id=%s reg=%s score=%.1f factors=%s",
            project.project_id,
            project.registration_number,
            opportunity_score,
            factor_scores,
        )

        return ScoredProject(
            **project.model_dump(),
            opportunity_score=opportunity_score,
            factor_scores=factor_scores,
            location_tier=tier,
        )

    def score_batch(
        self, projects: list[CleanProject]
    ) -> list[ScoredProject]:
        """Score a list of CleanProjects."""
        results = [self.score(p) for p in projects]
        if results:
            scores = [r.opportunity_score for r in results]
            logger.info(
                "Batch scored %d projects | min=%.1f | max=%.1f | mean=%.1f",
                len(results),
                min(scores),
                max(scores),
                sum(scores) / len(scores),
            )
        return results
