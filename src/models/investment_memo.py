"""
Structured investment memo produced by the AI analyst for one MAHARERA project.

All fields are populated by Claude based strictly on the provided project brief.
No field should contain information not present in the source ScoredProject
or its DeveloperProfile.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class RecommendedAction(str, Enum):
    FLAG_FOR_REVIEW = "FLAG_FOR_REVIEW"   # strong metrics, warrants analyst attention
    MONITOR = "MONITOR"                    # interesting but borderline or data gaps
    PASS = "PASS"                          # low score, lapsed, or no funding gap


class InvestmentMemo(BaseModel):
    """AI-generated investment assessment for one MAHARERA project.

    All analytical content is grounded in the structured fields from
    ScoredProject and DeveloperProfile — no invented facts.
    """

    # --- Source identifiers ---
    project_id: int
    registration_number: str
    project_name: str
    developer_name: str

    # --- AI-generated analysis ---
    recommended_action: RecommendedAction
    opportunity_thesis: str          # 2–3 sentences citing specific metrics
    risk_flags: list[str]            # each flag cites a data point
    data_gaps: list[str]             # fields that were null/missing in the brief
    confidence_score: float          # 0.0 (low) – 1.0 (high); reflects data completeness

    # --- Key metrics echoed back (from structured data, not AI-generated) ---
    opportunity_score: float
    track_record_score: Optional[float] = None
    construction_progress_pct: Optional[float] = None
    delay_days: Optional[int] = None
    extension_count: int = 0

    # --- Provenance ---
    model_used: str
    input_tokens: int
    output_tokens: int
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("risk_flags", "data_gaps", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        # Handle pipe-separated strings written by legacy CSV-style JSON serializer
        if isinstance(v, str):
            if not v or v.lower() in ("none", "null", "[]"):
                return []
            return [item.strip() for item in v.split("|") if item.strip()]
        return v

    model_config = {"frozen": True, "protected_namespaces": ()}
