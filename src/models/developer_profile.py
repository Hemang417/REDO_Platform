"""
Aggregated developer/promoter profile computed from a set of ScoredProjects.

Represents the full track record of a MAHARERA-registered developer:
portfolio size, delivery rates, delay statistics, geographic footprint,
and a composite track record score.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class DeveloperProfile(BaseModel):
    """Portfolio-level intelligence for one MAHARERA developer."""

    # --- Identity ---
    # Primary key: promoter_profile_id when available; None when grouped by name only
    promoter_profile_id: Optional[int] = None
    developer_name: str            # canonical name (most frequent across projects)

    # --- Portfolio composition ---
    total_projects: int
    active_projects: int
    completed_projects: int
    lapsed_projects: int
    deregistered_projects: int
    abeyance_projects: int

    # --- Delivery track record ---
    # Rates are None when the denominator is 0 (e.g. no projects with date info)
    completion_rate: Optional[float] = None      # completed / total
    on_time_rate: Optional[float] = None         # not-delayed / projects-with-date
    lapse_rate: Optional[float] = None           # lapsed / total
    avg_delay_days: Optional[float] = None       # mean delay across projects with date
    max_delay_days: Optional[int] = None         # worst single project
    avg_extensions: Optional[float] = None       # mean extensions per project

    # --- Construction health (active/ongoing projects only) ---
    avg_construction_progress: Optional[float] = None

    # --- Investment signal (from project scores) ---
    avg_opportunity_score: Optional[float] = None
    max_opportunity_score: Optional[float] = None

    # --- Geographic footprint ---
    districts: list[str]                         # all unique districts (sorted)
    primary_district: Optional[str] = None       # most frequent district

    # --- Track record score (0–100) ---
    track_record_score: float

    # --- Provenance ---
    project_ids: list[int]                       # all project_ids included
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    model_config = {"frozen": True}
