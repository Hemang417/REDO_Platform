"""
Upsert logic for RawProject/documents -> Postgres.

Never inserts duplicates: Projects are keyed on registration_number, Documents
are keyed on (project_id, doc_type). Re-running always updates in place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.database.models import (
    Project, Document, Professional, Complaint, Appeal, Partner, PastExperience, Spoc, SroDetail,
)
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


def upsert_projects(session: Session, projects: list[RawProject]) -> dict[str, int]:
    """Upsert a batch of RawProject records into the projects table.

    Uses Postgres's native ON CONFLICT DO UPDATE keyed on registration_number,
    so this is a single round-trip batch operation rather than N SELECT+INSERT/UPDATE pairs.

    Returns a dict mapping registration_number -> Project.id (DB primary key),
    so callers (e.g. the document downloader) can attach child rows without a
    second round-trip.
    """
    if not projects:
        return {}

    rows = [
        {"registration_number": p.registration_number, **{f: getattr(p, f) for f in _UPSERT_FIELDS}}
        for p in projects
    ]

    stmt = pg_insert(Project).values(rows)
    update_cols = {f: stmt.excluded[f] for f in _UPSERT_FIELDS}
    stmt = stmt.on_conflict_do_update(
        index_elements=["registration_number"],
        set_=update_cols,
    ).returning(Project.id, Project.registration_number)
    result = session.execute(stmt)
    id_by_reg_number = {reg_number: pk for pk, reg_number in result}
    session.commit()

    logger.info("Upserted %d projects into Postgres", len(rows))
    return id_by_reg_number


@dataclass
class DocumentRecord:
    project_id: int
    registration_number: str
    source_ref: str  # documentDmsRefNo — MAHARERA's globally unique document id
    file_name: str
    sha256: str
    local_path: str
    downloaded_at: datetime
    document_type_id: int | None = None
    doc_type: str | None = None
    uploaded_at: str | None = None


def upsert_documents(session: Session, documents: list[DocumentRecord]) -> int:
    """Upsert a batch of downloaded documents, keyed on source_ref (MAHARERA's
    own document id — globally unique, so this alone is a safe dedup key).

    Re-downloading an unchanged document is a no-op at the caller level (the
    downloader skips re-writing to disk if the sha256 on disk already matches);
    this upsert just makes sure the DB row reflects whatever was actually saved.
    """
    if not documents:
        return 0

    fields = ["project_id", "registration_number", "document_type_id", "doc_type",
              "file_name", "uploaded_at", "sha256", "local_path", "downloaded_at"]
    rows = [
        {"source_ref": d.source_ref, **{f: getattr(d, f) for f in fields}}
        for d in documents
    ]

    stmt = pg_insert(Document).values(rows)
    update_cols = {f: stmt.excluded[f] for f in fields}
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_ref"],
        set_=update_cols,
    )
    session.execute(stmt)
    session.commit()

    logger.info("Upserted %d documents into Postgres", len(rows))
    return len(rows)


@dataclass
class ProfessionalRecord:
    project_id: int
    registration_number: str
    promoter_professional_id: int
    professional_type_id: int | None = None
    first_name: str | None = None
    last_name: str | None = None
    entity_company_name: str | None = None
    architect_coa_registration_no: str | None = None
    engineer_license_no: str | None = None
    ca_icai_membership_no: str | None = None
    real_estate_agent_rera_reg_no: str | None = None


def upsert_professionals(session: Session, professionals: list[ProfessionalRecord]) -> int:
    """Upsert professionals, keyed on (project_id, promoter_professional_id)."""
    if not professionals:
        return 0

    fields = ["project_id", "registration_number", "professional_type_id", "first_name",
              "last_name", "entity_company_name", "architect_coa_registration_no",
              "engineer_license_no", "ca_icai_membership_no", "real_estate_agent_rera_reg_no"]
    rows = [
        {"promoter_professional_id": p.promoter_professional_id, **{f: getattr(p, f) for f in fields}}
        for p in professionals
    ]

    stmt = pg_insert(Professional).values(rows)
    update_cols = {f: stmt.excluded[f] for f in fields}
    stmt = stmt.on_conflict_do_update(
        index_elements=["project_id", "promoter_professional_id"],
        set_=update_cols,
    )
    session.execute(stmt)
    session.commit()

    logger.info("Upserted %d professionals into Postgres", len(rows))
    return len(rows)


@dataclass
class ComplaintRecord:
    project_id: int
    registration_number: str
    complaint_no: str
    raw_data: dict
    complaint_date: str | None = None
    complainant_name: str | None = None
    respondent_name: str | None = None
    complaint_status: str | None = None


def upsert_complaints(session: Session, complaints: list[ComplaintRecord]) -> int:
    """Upsert itemized complaints, keyed on (project_id, complaint_no)."""
    if not complaints:
        return 0

    fields = ["project_id", "registration_number", "complaint_date", "complainant_name",
              "respondent_name", "complaint_status", "raw_data"]
    rows = [
        {"complaint_no": c.complaint_no, **{f: getattr(c, f) for f in fields}}
        for c in complaints
    ]

    stmt = pg_insert(Complaint).values(rows)
    update_cols = {f: stmt.excluded[f] for f in fields}
    stmt = stmt.on_conflict_do_update(
        index_elements=["project_id", "complaint_no"],
        set_=update_cols,
    )
    session.execute(stmt)
    session.commit()

    logger.info("Upserted %d complaints into Postgres", len(rows))
    return len(rows)


@dataclass
class AppealRecord:
    project_id: int
    registration_number: str
    appeal_no: str
    raw_data: dict
    complaint_reference_no: str | None = None
    appeal_date: str | None = None
    appellant_name: str | None = None
    respondent_name: str | None = None
    appeal_status: str | None = None


def upsert_appeals(session: Session, appeals: list[AppealRecord]) -> int:
    """Upsert itemized appeals, keyed on (project_id, appeal_no)."""
    if not appeals:
        return 0

    fields = ["project_id", "registration_number", "complaint_reference_no", "appeal_date",
              "appellant_name", "respondent_name", "appeal_status", "raw_data"]
    rows = [
        {"appeal_no": a.appeal_no, **{f: getattr(a, f) for f in fields}}
        for a in appeals
    ]

    stmt = pg_insert(Appeal).values(rows)
    update_cols = {f: stmt.excluded[f] for f in fields}
    stmt = stmt.on_conflict_do_update(
        index_elements=["project_id", "appeal_no"],
        set_=update_cols,
    )
    session.execute(stmt)
    session.commit()

    logger.info("Upserted %d appeals into Postgres", len(rows))
    return len(rows)


@dataclass
class PartnerRecord:
    project_id: int
    registration_number: str
    personnel_id: int
    raw_data: dict
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    designation: str | None = None
    pan_number_encrypted: str | None = None
    mobile_number_encrypted: str | None = None
    email_hash: str | None = None
    din_number: str | None = None


def upsert_partners(session: Session, partners: list[PartnerRecord]) -> int:
    """Upsert promoter partners/directors, keyed on (project_id, personnel_id)."""
    if not partners:
        return 0

    fields = ["project_id", "registration_number", "first_name", "middle_name", "last_name",
              "designation", "pan_number_encrypted", "mobile_number_encrypted", "email_hash",
              "din_number", "raw_data"]
    rows = [
        {"personnel_id": p.personnel_id, **{f: getattr(p, f) for f in fields}}
        for p in partners
    ]

    stmt = pg_insert(Partner).values(rows)
    update_cols = {f: stmt.excluded[f] for f in fields}
    stmt = stmt.on_conflict_do_update(
        index_elements=["project_id", "personnel_id"],
        set_=update_cols,
    )
    session.execute(stmt)
    session.commit()

    logger.info("Upserted %d partners into Postgres", len(rows))
    return len(rows)


@dataclass
class PastExperienceRecord:
    project_id: int
    registration_number: str
    past_experience_id: int
    raw_data: dict
    past_project_name: str | None = None
    address: str | None = None
    land_area: str | None = None
    number_of_buildings_plots: str | None = None
    number_of_apartments: str | None = None
    total_cost: str | None = None
    original_proposed_completion_date: str | None = None
    actual_completion_date: str | None = None
    past_project_type_name: str | None = None
    past_project_status: str | None = None
    is_project_has_litigation: str | None = None
    is_registered_with_maharera: str | None = None
    maharera_registration_number: str | None = None


def upsert_past_experiences(session: Session, records: list[PastExperienceRecord]) -> int:
    """Upsert promoter past-experience projects, keyed on (project_id, past_experience_id)."""
    if not records:
        return 0

    fields = ["project_id", "registration_number", "past_project_name", "address", "land_area",
              "number_of_buildings_plots", "number_of_apartments", "total_cost",
              "original_proposed_completion_date", "actual_completion_date",
              "past_project_type_name", "past_project_status", "is_project_has_litigation",
              "is_registered_with_maharera", "maharera_registration_number", "raw_data"]
    rows = [
        {"past_experience_id": r.past_experience_id, **{f: getattr(r, f) for f in fields}}
        for r in records
    ]

    stmt = pg_insert(PastExperience).values(rows)
    update_cols = {f: stmt.excluded[f] for f in fields}
    stmt = stmt.on_conflict_do_update(
        index_elements=["project_id", "past_experience_id"],
        set_=update_cols,
    )
    session.execute(stmt)
    session.commit()

    logger.info("Upserted %d past-experience records into Postgres", len(rows))
    return len(rows)


@dataclass
class SpocRecord:
    project_id: int
    registration_number: str
    spoc_id: str
    raw_data: dict
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    designation: str | None = None
    spoc_type: str | None = None
    mobile_number: str | None = None
    email: str | None = None
    pan_number: str | None = None


def upsert_spocs(session: Session, records: list[SpocRecord]) -> int:
    """Upsert SPOC records, keyed on (project_id, spoc_id)."""
    if not records:
        return 0

    fields = ["project_id", "registration_number", "first_name", "middle_name", "last_name",
              "designation", "spoc_type", "mobile_number", "email", "pan_number", "raw_data"]
    rows = [
        {"spoc_id": r.spoc_id, **{f: getattr(r, f) for f in fields}}
        for r in records
    ]

    stmt = pg_insert(Spoc).values(rows)
    update_cols = {f: stmt.excluded[f] for f in fields}
    stmt = stmt.on_conflict_do_update(
        index_elements=["project_id", "spoc_id"],
        set_=update_cols,
    )
    session.execute(stmt)
    session.commit()

    logger.info("Upserted %d SPOC records into Postgres", len(rows))
    return len(rows)


@dataclass
class SroDetailRecord:
    project_id: int
    registration_number: str
    sro_id: str
    raw_data: dict


def upsert_sro_details(session: Session, records: list[SroDetailRecord]) -> int:
    """Upsert SRO detail records, keyed on (project_id, sro_id). Raw-data-only
    until a populated record confirms the real field names (see SroDetail model
    docstring)."""
    if not records:
        return 0

    fields = ["project_id", "registration_number", "raw_data"]
    rows = [
        {"sro_id": r.sro_id, **{f: getattr(r, f) for f in fields}}
        for r in records
    ]

    stmt = pg_insert(SroDetail).values(rows)
    update_cols = {f: stmt.excluded[f] for f in fields}
    stmt = stmt.on_conflict_do_update(
        index_elements=["project_id", "sro_id"],
        set_=update_cols,
    )
    session.execute(stmt)
    session.commit()

    logger.info("Upserted %d SRO detail records into Postgres", len(rows))
    return len(rows)
