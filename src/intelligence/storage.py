"""
Writes DeveloperProfile records to output/intelligence/ as JSON and CSV.
Atomic write pattern: .tmp → os.replace()
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.models.developer_profile import DeveloperProfile

logger = logging.getLogger(__name__)

_CSV_FIELDS = [
    "track_record_score",
    "promoter_profile_id",
    "developer_name",
    "primary_district",
    "total_projects",
    "active_projects",
    "completed_projects",
    "lapsed_projects",
    "completion_rate",
    "on_time_rate",
    "lapse_rate",
    "avg_delay_days",
    "max_delay_days",
    "avg_extensions",
    "avg_construction_progress",
    "avg_opportunity_score",
    "max_opportunity_score",
    "districts",
    "computed_at",
]


def _serialise_json(value: Any) -> Any:
    """For JSON: keep lists as lists; convert dates to ISO strings."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _serialise_csv(value: Any) -> Any:
    """For CSV: flatten lists to semicolon-separated strings."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return value


class IntelligenceStorage:
    """Writes DeveloperProfile records to output/intelligence/."""

    def __init__(self, output_dir: str) -> None:
        self._dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def save(
        self,
        profiles: list[DeveloperProfile],
        run_id: str,
        json_enabled: bool = True,
        csv_enabled: bool = True,
    ) -> dict[str, str]:
        if not profiles:
            return {}

        paths: dict[str, str] = {}
        base = os.path.join(self._dir, f"developer_profiles_{run_id}")

        if json_enabled:
            paths["json"] = self._write_json(profiles, base)
        if csv_enabled:
            paths["csv"] = self._write_csv(profiles, base)

        logger.info(
            "Saved %d developer profiles | run_id=%s | paths=%s",
            len(profiles),
            run_id,
            {k: os.path.basename(v) for k, v in paths.items()},
        )
        return paths

    def _write_json(self, profiles: list[DeveloperProfile], base: str) -> str:
        path = f"{base}.json"
        tmp = f"{base}.json.tmp"
        records = [
            {k: _serialise_json(v) for k, v in p.model_dump().items()}
            for p in profiles
        ]
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)
        return path

    def _write_csv(self, profiles: list[DeveloperProfile], base: str) -> str:
        path = f"{base}.csv"
        tmp = f"{base}.csv.tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for p in profiles:
                row = {k: _serialise_csv(v) for k, v in p.model_dump().items()}
                writer.writerow(row)
        os.replace(tmp, path)
        return path
