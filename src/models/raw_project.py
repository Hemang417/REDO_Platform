"""
Pydantic model for a single raw MAHARERA project record.

This is the contract between the scraper (Module 1) and all downstream modules.

Design principles:
- All fields are raw strings or None — no date parsing, no numeric coercion.
  Type coercion belongs in Module 2 (the cleaning layer).
- Field names are clean English, not MAHARERA API names (those are full of typos).
- The model validates that required identifiers are present and strips whitespace.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class RawProject(BaseModel):
    """One MAHARERA project as collected from the public portal.

    Fields from the list page:
        registration_number, project_name, developer_name, district,
        last_modified, detail_url, project_id

    Fields from the detail API:
        taluka, state, village, project_type,
        status_name, current_status, is_lapsed, is_deregistered, is_abeyance,
        proposed_completion_date, original_completion_date, registration_date,
        construction_progress_pct, extension_count,
        promoter_profile_id

    Provenance:
        source_url: the maharerait detail page URL
        scraped_at: UTC timestamp when this record was collected
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    # --- Identifiers ---
    project_id: str
    registration_number: str

    # --- List page fields ---
    project_name: str
    developer_name: str
    district: str
    last_modified: Optional[str] = None
    detail_url: str

    # --- Detail API fields ---
    taluka: Optional[str] = None
    state: Optional[str] = None
    village: Optional[str] = None
    project_type: Optional[str] = None

    # Status fields
    status_name: Optional[str] = None           # from general details ("Ongoing", "New", etc.)
    current_status: Optional[str] = None        # from current status API ("Active", "Completed", etc.)
    is_lapsed: Optional[str] = None             # "0" or "1"
    is_deregistered: Optional[str] = None       # "0" or "1"
    is_abeyance: Optional[str] = None           # "0" or "1"

    # Date fields (stored as raw strings)
    proposed_completion_date: Optional[str] = None
    original_completion_date: Optional[str] = None
    registration_date: Optional[str] = None

    # Progress and extensions
    construction_progress_pct: Optional[str] = None  # average across activities, e.g. "67.5"
    extension_count: Optional[str] = None             # e.g. "2"

    # Litigation / legal flags (from MAHARERA getProjectLitigationDetails,
    # getComplaintDetailsByProjectId, and promoter isAnyCriminalCases endpoints)
    is_litigation_present: Optional[str] = None   # "0" or "1"
    is_litigation_declared: Optional[str] = None  # "0" or "1"
    complaint_count: Optional[str] = None         # integer as string
    is_criminal_cases: Optional[str] = None       # "0" or "1"

    # Developer profile ID (used for developer intelligence module)
    promoter_profile_id: Optional[str] = None

    # Provenance
    source_url: str
    scraped_at: datetime

    @field_validator("project_id", "registration_number")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("project_id and registration_number must not be empty")
        return v
