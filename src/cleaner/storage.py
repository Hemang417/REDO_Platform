"""
Writes CleanProject records to output/clean/ as JSON and CSV.

Same atomic-write pattern as src/scraper/storage.py:
  write to .tmp → os.replace() → no corrupt files on crash.

Single responsibility: serialisation and file I/O only.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.config.loader import CleanerConfig
from src.models.clean_project import CleanProject

logger = logging.getLogger(__name__)

_CSV_FIELDS = [
    "project_id",
    "registration_number",
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
    "last_modified",
    "construction_progress_pct",
    "extension_count",
    "delay_days",
    "is_delayed",
    "promoter_profile_id",
    "detail_url",
    "source_url",
    "scraped_at",
    "cleaned_at",
]


def _serialise(value: Any) -> Any:
    """JSON-serialise dates and datetimes; pass everything else through."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


class CleanStorage:
    """Writes cleaned project records to output/clean/ as JSON and/or CSV."""

    def __init__(self, config: CleanerConfig) -> None:
        self._cfg = config
        Path(config.clean_output_dir).mkdir(parents=True, exist_ok=True)

    def save(
        self,
        projects: list[CleanProject],
        run_id: str,
        append: bool = False,
    ) -> dict[str, str]:
        """Persist cleaned projects.

        Args:
            projects: Cleaned records to write.
            run_id:   Run identifier (used in filename).
            append:   If True, merge with any existing file for this run_id.

        Returns:
            Dict of format → absolute file path for each file written.
        """
        if not projects:
            return {}

        paths: dict[str, str] = {}
        base = os.path.join(self._cfg.clean_output_dir, f"maharera_clean_{run_id}")

        if self._cfg.json_enabled:
            path = self._write_json(projects, base, append)
            paths["json"] = path

        if self._cfg.csv_enabled:
            path = self._write_csv(projects, base, append)
            paths["csv"] = path

        logger.info(
            "Saved %d clean projects | run_id=%s | paths=%s",
            len(projects),
            run_id,
            {k: os.path.basename(v) for k, v in paths.items()},
        )
        return paths

    def _write_json(
        self, projects: list[CleanProject], base: str, append: bool
    ) -> str:
        json_path = f"{base}.json"
        tmp_path = f"{base}.json.tmp"

        existing: list[dict] = []
        if append and os.path.exists(json_path):
            try:
                with open(json_path, encoding="utf-8") as fh:
                    existing = json.load(fh)
            except (json.JSONDecodeError, OSError):
                logger.warning("Could not read existing JSON for append; overwriting.")
                existing = []

        records = existing + [
            {k: _serialise(v) for k, v in p.model_dump().items()}
            for p in projects
        ]

        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2, default=_serialise)

        os.replace(tmp_path, json_path)
        return json_path

    def _write_csv(
        self, projects: list[CleanProject], base: str, append: bool
    ) -> str:
        csv_path = f"{base}.csv"
        tmp_path = f"{base}.csv.tmp"

        write_header = not (append and os.path.exists(csv_path))

        with open(tmp_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            for p in projects:
                row = {k: _serialise(v) for k, v in p.model_dump().items()}
                writer.writerow(row)

        if append and os.path.exists(csv_path):
            with open(csv_path, "a", newline="", encoding="utf-8") as out, \
                 open(tmp_path, "r", newline="", encoding="utf-8") as inp:
                out.write(inp.read())
            os.remove(tmp_path)
        else:
            os.replace(tmp_path, csv_path)

        return csv_path

    def save_failed(self, failed: list, run_id: str) -> None:
        """Write uncleanable raw records to a separate JSON for investigation."""
        if not failed:
            return
        path = os.path.join(
            self._cfg.clean_output_dir, f"maharera_clean_failed_{run_id}.json"
        )
        tmp = path + ".tmp"
        records = [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in failed]
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)
        logger.info("Saved %d failed records to %s", len(failed), path)
