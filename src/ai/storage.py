"""
Writes InvestmentMemo records to output/memos/ as JSON and CSV.
Atomic write pattern: .tmp → os.replace()
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.investment_memo import InvestmentMemo

logger = logging.getLogger(__name__)

_CSV_FIELDS = [
    "recommended_action",
    "opportunity_score",
    "confidence_score",
    "project_id",
    "registration_number",
    "project_name",
    "developer_name",
    "construction_progress_pct",
    "delay_days",
    "extension_count",
    "track_record_score",
    "opportunity_thesis",
    "risk_flags",
    "data_gaps",
    "model_used",
    "input_tokens",
    "output_tokens",
    "generated_at",
]


def _serialise_json(value: Any) -> Any:
    """For JSON: keep lists as lists; convert dates to ISO strings."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialise_csv(value: Any) -> Any:
    """For CSV: flatten lists to pipe-separated strings."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    return value


class MemoStorage:
    """Writes InvestmentMemo records to output/memos/."""

    def __init__(self, output_dir: str) -> None:
        self._dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def save(
        self,
        memos: list[InvestmentMemo],
        run_id: str,
    ) -> dict[str, str]:
        if not memos:
            return {}

        paths: dict[str, str] = {}
        base = os.path.join(self._dir, f"investment_memos_{run_id}")

        paths["json"] = self._write_json(memos, base)
        paths["csv"] = self._write_csv(memos, base)

        logger.info(
            "Saved %d investment memos | run_id=%s",
            len(memos),
            run_id,
        )
        return paths

    def _write_json(self, memos: list[InvestmentMemo], base: str) -> str:
        path = f"{base}.json"
        tmp = f"{base}.json.tmp"
        records = [
            {k: _serialise_json(v) for k, v in m.model_dump().items()}
            for m in memos
        ]
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)
        return path

    def _write_csv(self, memos: list[InvestmentMemo], base: str) -> str:
        path = f"{base}.csv"
        tmp = f"{base}.csv.tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for m in memos:
                writer.writerow({k: _serialise_csv(v) for k, v in m.model_dump().items()})
        os.replace(tmp, path)
        return path
