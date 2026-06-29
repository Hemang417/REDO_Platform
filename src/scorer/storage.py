"""
Writes ScoredProject records to output/scored/ as JSON and CSV.

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

from src.models.scored_project import ScoredProject

logger = logging.getLogger(__name__)

_CSV_FIELDS = [
    "opportunity_score",
    "location_tier",
    "project_id",
    "registration_number",
    "project_name",
    "developer_name",
    "district",
    "taluka",
    "project_type",
    "current_status",
    "is_lapsed",
    "is_deregistered",
    "proposed_completion_date",
    "construction_progress_pct",
    "delay_days",
    "is_delayed",
    "extension_count",
    "registration_date",
    "detail_url",
    "scraped_at",
    "scored_at",
    # Factor scores — flattened
    "score_construction_progress",
    "score_delay_severity",
    "score_extension_history",
    "score_project_viability",
    "score_location",
]


def _serialise(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _flatten(project: ScoredProject) -> dict:
    """Flatten factor_scores dict into top-level CSV columns."""
    row = {k: _serialise(v) for k, v in project.model_dump().items() if k != "factor_scores"}
    for factor, score in project.factor_scores.items():
        row[f"score_{factor}"] = score
    return row


class ScoredStorage:
    """Writes ScoredProject records to output/scored/."""

    def __init__(self, output_dir: str) -> None:
        self._dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def save(
        self,
        projects: list[ScoredProject],
        run_id: str,
        json_enabled: bool = True,
        csv_enabled: bool = True,
    ) -> dict[str, str]:
        if not projects:
            return {}

        paths: dict[str, str] = {}
        base = os.path.join(self._dir, f"maharera_scored_{run_id}")

        if json_enabled:
            paths["json"] = self._write_json(projects, base)
        if csv_enabled:
            paths["csv"] = self._write_csv(projects, base)

        logger.info(
            "Saved %d scored projects | run_id=%s | paths=%s",
            len(projects),
            run_id,
            {k: os.path.basename(v) for k, v in paths.items()},
        )
        return paths

    def _write_json(self, projects: list[ScoredProject], base: str) -> str:
        path = f"{base}.json"
        tmp = f"{base}.json.tmp"
        records = [
            {k: _serialise(v) for k, v in p.model_dump().items()}
            for p in projects
        ]
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2, default=_serialise)
        os.replace(tmp, path)
        return path

    def _write_csv(self, projects: list[ScoredProject], base: str) -> str:
        path = f"{base}.csv"
        tmp = f"{base}.csv.tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for p in projects:
                writer.writerow(_flatten(p))
        os.replace(tmp, path)
        return path
