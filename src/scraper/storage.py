"""
Writes collected RawProject records to disk as JSON and CSV.

Design principles:
- Atomic writes: writes to .tmp file first, then os.replace() to final path.
  This prevents corrupt output files if the process is killed mid-write.
- Appends on checkpoint: the run_id ties all checkpoint files together.
- Each call to save() flushes the current batch — caller controls frequency.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config.loader import StorageConfig
from src.models.raw_project import RawProject

logger = logging.getLogger(__name__)

# Ordered list of CSV columns — matches RawProject fields
_CSV_FIELDS = [
    "project_id",
    "registration_number",
    "project_name",
    "developer_name",
    "district",
    "taluka",
    "state",
    "project_type",
    "status_name",
    "current_status",
    "is_lapsed",
    "is_deregistered",
    "is_abeyance",
    "construction_progress_pct",
    "proposed_completion_date",
    "original_completion_date",
    "registration_date",
    "extension_count",
    "last_modified",
    "promoter_profile_id",
    "detail_url",
    "source_url",
    "scraped_at",
]


class RawStorage:
    """Persists RawProject records to JSON and CSV files.

    File names include the run_id so multiple partial runs do not overwrite each other.
    """

    def __init__(self, config: StorageConfig) -> None:
        self._config = config
        self._output_dir = Path(config.raw_output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        projects: list[RawProject],
        run_id: str,
        append: bool = False,
    ) -> dict[str, Optional[str]]:
        """Write a list of projects to JSON and/or CSV.

        Args:
            projects: The batch of projects to persist.
            run_id: A unique identifier for this scraper run (UTC timestamp string).
            append: If True, append to existing files; otherwise overwrite.

        Returns:
            Dict mapping format name to output file path (or None if disabled).
        """
        if not projects:
            logger.debug("save() called with empty project list — skipping")
            return {}

        paths: dict[str, Optional[str]] = {}

        if self._config.json_enabled:
            paths["json"] = self._save_json(projects, run_id, append)

        if self._config.csv_enabled:
            paths["csv"] = self._save_csv(projects, run_id, append)

        logger.info(
            "Saved %d projects | run_id=%s | paths=%s",
            len(projects),
            run_id,
            {k: Path(v).name for k, v in paths.items() if v},
        )
        return paths

    def _save_json(self, projects: list[RawProject], run_id: str, append: bool) -> str:
        final_path = self._output_dir / f"maharera_projects_{run_id}.json"
        tmp_path = Path(str(final_path) + ".tmp")

        existing: list[dict] = []
        if append and final_path.exists():
            try:
                with final_path.open("r", encoding="utf-8") as fh:
                    existing = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not read existing JSON for append: %s", exc)
                existing = []

        new_records = [p.model_dump(mode="json") for p in projects]
        combined = existing + new_records

        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(combined, fh, indent=2, ensure_ascii=False, default=str)

        os.replace(tmp_path, final_path)
        return str(final_path)

    def _save_csv(self, projects: list[RawProject], run_id: str, append: bool) -> str:
        final_path = self._output_dir / f"maharera_projects_{run_id}.csv"
        tmp_path = Path(str(final_path) + ".tmp")

        write_header = not (append and final_path.exists())

        # Copy existing content to tmp if appending
        if append and final_path.exists():
            import shutil
            shutil.copy2(final_path, tmp_path)
            write_header = False

        mode = "a" if (append and tmp_path.exists()) else "w"
        with tmp_path.open(mode, encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            for project in projects:
                row = project.model_dump(mode="json")
                # Ensure all fields are present
                writer.writerow({f: row.get(f, "") for f in _CSV_FIELDS})

        os.replace(tmp_path, final_path)
        return str(final_path)

    def save_failed_urls(self, failed: list[dict], run_id: str) -> None:
        """Append failed project stubs to a text file for later retry."""
        failed_path = self._output_dir / f"failed_projects_{run_id}.txt"
        with failed_path.open("a", encoding="utf-8") as fh:
            for item in failed:
                fh.write(f"{item.get('project_id', '?')} | {item.get('detail_url', '?')}\n")
        logger.warning("Logged %d failed projects to %s", len(failed), failed_path.name)
