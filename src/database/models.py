"""
SQLAlchemy 2.0 models for the MAHARERA warehouse.

Scoped to fields confirmed by the existing scraper (RawProject). Additional
tables (directors, engineers, contractors, quarterly updates, documents) are
intentionally NOT included yet — they require live-site discovery to confirm
they exist as separate API responses before a schema is written for them.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, UniqueConstraint
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
