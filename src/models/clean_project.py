"""
Typed, validated representation of a MAHARERA project after cleaning.

All fields that were raw strings in RawProject now carry their proper Python types.
This is the contract between Module 2 (cleaning) and all downstream modules
(scoring, AI analysis, storage).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class CleanProject(BaseModel):
    """A fully typed, normalised MAHARERA project record.

    Downstream modules treat this as immutable — use model_copy(update={...})
    if a field needs to change rather than mutating in-place.
    """

    # --- Identity ---
    project_id: int
    registration_number: str
    promoter_profile_id: Optional[int] = None

    # --- Names (normalised: stripped, upper-cased) ---
    project_name: str
    developer_name: str

    # --- Location (normalised: stripped, title-cased) ---
    district: str
    taluka: Optional[str] = None
    state: Optional[str] = None
    village: Optional[str] = None

    # --- Classification ---
    project_type: Optional[str] = None
    status_name: Optional[str] = None
    current_status: Optional[str] = None

    # --- Status flags ---
    is_lapsed: Optional[bool] = None
    is_deregistered: Optional[bool] = None
    is_abeyance: Optional[bool] = None

    # --- Dates ---
    proposed_completion_date: Optional[date] = None
    original_completion_date: Optional[date] = None
    registration_date: Optional[date] = None
    last_modified: Optional[date] = None

    # --- Progress metrics ---
    construction_progress_pct: Optional[float] = None
    extension_count: int = 0

    # --- Litigation / legal flags (from MAHARERA litigation endpoints) ---
    is_litigation_present: bool = False
    is_litigation_declared: bool = False
    complaint_count: int = 0
    is_criminal_cases: bool = False

    # --- Derived fields (computed during cleaning) ---
    delay_days: Optional[int] = None
    is_delayed: Optional[bool] = None

    # --- Provenance ---
    detail_url: str
    source_url: str
    scraped_at: datetime
    cleaned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    model_config = {"frozen": True}
