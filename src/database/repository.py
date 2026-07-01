"""
Upsert logic for RawProject -> Postgres, keyed on registration_number.

Never inserts duplicates: if a registration_number already exists, the row
is updated in place (and updated_at bumped); otherwise a new row is inserted.
"""

from __future__ import annotations

import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.database.models import Project
from src.models.raw_project import RawProject

logger = logging.getLogger(__name__)

_UPSERT_FIELDS = [
    "project_id",
    "project_name",
    "developer_name",
    "district",
    "taluka",
    "state",
    "village",
    "project_type",
    "status_name",
    "current_status",
    "is_lapsed",
    "is_deregistered",
    "is_abeyance",
    "proposed_completion_date",
    "original_completion_date",
    "registration_date",
    "construction_progress_pct",
    "extension_count",
    "is_litigation_present",
    "is_litigation_declared",
    "complaint_count",
    "is_criminal_cases",
    "promoter_profile_id",
    "last_modified",
    "detail_url",
    "source_url",
    "scraped_at",
]


def upsert_projects(session: Session, projects: list[RawProject]) -> int:
    """Upsert a batch of RawProject records into the projects table.

    Uses Postgres's native ON CONFLICT DO UPDATE keyed on registration_number,
    so this is a single round-trip batch operation rather than N SELECT+INSERT/UPDATE pairs.

    Returns the number of rows affected.
    """
    if not projects:
        return 0

    rows = [
        {"registration_number": p.registration_number, **{f: getattr(p, f) for f in _UPSERT_FIELDS}}
        for p in projects
    ]

    stmt = pg_insert(Project).values(rows)
    update_cols = {f: stmt.excluded[f] for f in _UPSERT_FIELDS}
    stmt = stmt.on_conflict_do_update(
        index_elements=["registration_number"],
        set_=update_cols,
    )
    session.execute(stmt)
    session.commit()

    logger.info("Upserted %d projects into Postgres", len(rows))
    return len(rows)
