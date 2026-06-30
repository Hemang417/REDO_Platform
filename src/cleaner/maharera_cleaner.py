"""
Maps RawProject (all str | None) to CleanProject (typed, normalised).

Single responsibility: field-by-field coercion using field_parsers.
No I/O, no HTTP calls, no business rules beyond what's in config.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from src.cleaner.field_parsers import (
    compute_delay_days,
    normalise_location,
    normalise_name,
    parse_bool,
    parse_date,
    parse_float,
    parse_int,
)
from src.config.loader import CleanerConfig
from src.models.clean_project import CleanProject
from src.models.raw_project import RawProject

logger = logging.getLogger(__name__)


class MahareraCleaner:
    """Converts RawProject records to CleanProject records.

    Inject config so date formats are controlled from settings.yaml.
    """

    def __init__(self, config: CleanerConfig) -> None:
        self._date_formats = config.date_formats

    def clean(self, raw: RawProject) -> Optional[CleanProject]:
        """Convert one RawProject to CleanProject.

        Returns None only if project_id is unparseable (record is unusable).
        All other parse failures produce None fields — the record is kept.
        """
        project_id = parse_int(raw.project_id, "project_id")
        if project_id is None:
            logger.warning(
                "Dropping record: unparseable project_id=%r reg=%s",
                raw.project_id,
                raw.registration_number,
            )
            return None

        proposed = parse_date(raw.proposed_completion_date, self._date_formats, "proposed_completion_date")
        delay_days = compute_delay_days(proposed)

        return CleanProject(
            project_id=project_id,
            registration_number=raw.registration_number or "",
            promoter_profile_id=parse_int(raw.promoter_profile_id, "promoter_profile_id"),

            project_name=normalise_name(raw.project_name),
            developer_name=normalise_name(raw.developer_name),

            district=normalise_location(raw.district) or "",
            taluka=normalise_location(raw.taluka),
            state=normalise_location(raw.state),
            village=normalise_location(raw.village),

            project_type=raw.project_type.strip() if raw.project_type else None,
            status_name=raw.status_name.strip() if raw.status_name else None,
            current_status=raw.current_status.strip() if raw.current_status else None,

            is_lapsed=parse_bool(raw.is_lapsed, "is_lapsed"),
            is_deregistered=parse_bool(raw.is_deregistered, "is_deregistered"),
            is_abeyance=parse_bool(raw.is_abeyance, "is_abeyance"),

            proposed_completion_date=proposed,
            original_completion_date=parse_date(raw.original_completion_date, self._date_formats, "original_completion_date"),
            registration_date=parse_date(raw.registration_date, self._date_formats, "registration_date"),
            last_modified=parse_date(raw.last_modified, self._date_formats, "last_modified"),

            construction_progress_pct=parse_float(
                raw.construction_progress_pct,
                "construction_progress_pct",
                min_val=0.0,
                max_val=100.0,
            ),
            extension_count=parse_int(raw.extension_count, "extension_count") or 0,

            is_litigation_present=parse_bool(raw.is_litigation_present, "is_litigation_present") or False,
            is_litigation_declared=parse_bool(raw.is_litigation_declared, "is_litigation_declared") or False,
            complaint_count=parse_int(raw.complaint_count, "complaint_count") or 0,
            is_criminal_cases=parse_bool(raw.is_criminal_cases, "is_criminal_cases") or False,

            delay_days=delay_days,
            is_delayed=delay_days > 0 if delay_days is not None else None,

            detail_url=raw.detail_url or "",
            source_url=raw.source_url or "",
            scraped_at=raw.scraped_at if isinstance(raw.scraped_at, datetime)
                       else datetime.now(timezone.utc),
            cleaned_at=datetime.now(timezone.utc),
        )

    def clean_batch(self, raws: list[RawProject]) -> tuple[list[CleanProject], list[RawProject]]:
        """Clean a list of RawProjects.

        Returns:
            (cleaned, failed) — failed contains records that could not be cleaned.
        """
        cleaned: list[CleanProject] = []
        failed: list[RawProject] = []
        for raw in raws:
            result = self.clean(raw)
            if result is not None:
                cleaned.append(result)
            else:
                failed.append(raw)
        logger.info(
            "Batch clean complete | cleaned=%d | failed=%d | total=%d",
            len(cleaned),
            len(failed),
            len(raws),
        )
        return cleaned, failed
