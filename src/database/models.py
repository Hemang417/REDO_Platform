"""
SQLAlchemy 2.0 models for the MAHARERA warehouse.

Scoped to fields confirmed by the existing scraper (RawProject), plus tables
confirmed via live authenticated discovery of the detail SPA on 2026-07-02:
Document (getUploadedDocuments + downloadDocumentForPublicView), Professional
(getProjectProfessionalByType — architects/engineers/CAs/agents), Complaint
(itemized, getComplaintByProjectId), Appeal (getAppealDetailsPublicView).
Partner/SRO details (getProjectSroDetails) remain unconfirmed — the request
parameter format wasn't cracked during discovery — and are intentionally
NOT modeled yet.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, UniqueConstraint, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Project(Base):
    """One MAHARERA project. Mirrors src.models.raw_project.RawProject.

    registration_number is the natural dedup key — MAHARERA project_ids
    have been observed to be stable, but registration_number is what the
    site itself treats as the unique project identifier.
    """

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("registration_number", name="uq_projects_registration_number"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    project_id: Mapped[str] = mapped_column(String(64), index=True)
    registration_number: Mapped[str] = mapped_column(String(64), index=True)

    project_name: Mapped[str] = mapped_column(String(512))
    developer_name: Mapped[str] = mapped_column(String(512))
    district: Mapped[str] = mapped_column(String(128))
    taluka: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    village: Mapped[str | None] = mapped_column(String(128), nullable=True)
    project_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    status_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_lapsed: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_deregistered: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_abeyance: Mapped[str | None] = mapped_column(String(8), nullable=True)

    proposed_completion_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    original_completion_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    registration_date: Mapped[str | None] = mapped_column(String(64), nullable=True)

    construction_progress_pct: Mapped[str | None] = mapped_column(String(16), nullable=True)
    extension_count: Mapped[str | None] = mapped_column(String(16), nullable=True)

    is_litigation_present: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_litigation_declared: Mapped[str | None] = mapped_column(String(8), nullable=True)
    complaint_count: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_criminal_cases: Mapped[str | None] = mapped_column(String(8), nullable=True)

    promoter_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    last_modified: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail_url: Mapped[str] = mapped_column(String(1024))
    source_url: Mapped[str] = mapped_column(String(1024))

    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Document(Base):
    """A document (PDF) belonging to a project, sourced from getUploadedDocuments
    and downloaded via downloadDocumentForPublicView.

    source_ref is MAHARERA's own document identifier (documentDmsRefNo, a UUID) —
    globally unique per document, so it's the natural dedup key: safe to upsert
    without ever creating a duplicate row for the same underlying MAHARERA document.
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_ref", name="uq_documents_source_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    registration_number: Mapped[str] = mapped_column(String(64), index=True)

    source_ref: Mapped[str] = mapped_column(String(128), index=True)  # documentDmsRefNo
    document_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(256), nullable=True)  # documentDetails/documentDescription
    file_name: Mapped[str] = mapped_column(String(512))
    uploaded_at: Mapped[str | None] = mapped_column(String(64), nullable=True)  # MAHARERA's uploadDate, raw string

    sha256: Mapped[str] = mapped_column(String(64))
    local_path: Mapped[str] = mapped_column(String(1024))

    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Professional(Base):
    """An architect/engineer/CA/real-estate-agent associated with a project
    (from getProjectProfessionalByType). Dedup key: (project_id, promoter_professional_id)
    — MAHARERA's own per-project professional record id.
    """

    __tablename__ = "professionals"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "promoter_professional_id",
            name="uq_professionals_project_id_promoter_professional_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    registration_number: Mapped[str] = mapped_column(String(64), index=True)

    promoter_professional_id: Mapped[int] = mapped_column(Integer)
    professional_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    entity_company_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    architect_coa_registration_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    engineer_license_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ca_icai_membership_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    real_estate_agent_rera_reg_no: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Complaint(Base):
    """An itemized complaint against a project (getComplaintByProjectId).

    NOTE: the exact JSON field names below are best-effort — the project used for
    live discovery (P50500000005) had zero complaints, so the response shape could
    only be inferred from the rendered page's column headers, not a real payload.
    raw_data preserves the full untouched API record so nothing is lost if the
    typed field mapping turns out to be wrong; fix the mapping once real complaint
    records are observed, no backfill needed since raw_data already has everything.

    Dedup key: (project_id, complaint_no) — falls back to a synthetic key if
    MAHARERA's own complaint number field is missing on a given record.
    """

    __tablename__ = "complaints"
    __table_args__ = (
        UniqueConstraint("project_id", "complaint_no", name="uq_complaints_project_id_complaint_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    registration_number: Mapped[str] = mapped_column(String(64), index=True)

    complaint_no: Mapped[str] = mapped_column(String(128))
    complaint_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    complainant_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    respondent_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    complaint_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Appeal(Base):
    """An itemized appeal filed against a project's RERA decisions
    (getAppealDetailsPublicView).

    NOTE: same caveat as Complaint — field names are best-effort (inferred from
    page headers, not a real payload, since this project had zero appeals).
    raw_data preserves the full untouched API record.

    Dedup key: (project_id, appeal_no).
    """

    __tablename__ = "appeals"
    __table_args__ = (
        UniqueConstraint("project_id", "appeal_no", name="uq_appeals_project_id_appeal_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    registration_number: Mapped[str] = mapped_column(String(64), index=True)

    appeal_no: Mapped[str] = mapped_column(String(128))
    complaint_reference_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    appeal_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    appellant_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    respondent_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    appeal_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
