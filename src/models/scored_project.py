"""
A CleanProject augmented with investment opportunity scores.

All score fields are additive to CleanProject — no raw data is modified.
factor_scores provides the per-dimension breakdown for explainability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import Field

from src.models.clean_project import CleanProject


class ScoredProject(CleanProject):
    """A CleanProject with an investment opportunity score and factor breakdown."""

    # Weighted sum of all factor scores, normalised to [0, 100].
    # Higher = stronger AIF investment candidate.
    opportunity_score: float

    # Per-factor scores [0.0, 1.0] — key is the factor name from ScoringWeights.
    # Included for full explainability: analysts can see why a score is high/low.
    factor_scores: dict[str, float]

    # Tier label derived from location config: "tier1", "tier2", or "other"
    location_tier: str

    scored_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    model_config = {"frozen": True}
