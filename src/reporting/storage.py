"""
Writes the deal origination report to output/reports/ as HTML and JSON.
Atomic write pattern: .tmp -> os.replace()
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from src.reporting.report_builder import ReportData

logger = logging.getLogger(__name__)


class ReportStorage:
    """Writes rendered report files to output/reports/."""

    def __init__(self, output_dir: str) -> None:
        self._dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def save(
        self,
        data: ReportData,
        html_content: str,
        run_id: str,
    ) -> dict[str, str]:
        """Write HTML report and JSON summary. Returns paths dict."""
        base = os.path.join(self._dir, f"deal_origination_{run_id}")
        paths: dict[str, str] = {}

        paths["html"] = self._write_html(html_content, base)
        paths["json"] = self._write_json(data, base)

        logger.info(
            "Report saved | run_id=%s | flag=%d | monitor=%d | pass=%d",
            run_id,
            data.summary.flag_for_review_count,
            data.summary.monitor_count,
            data.summary.pass_count,
        )
        return paths

    def _write_html(self, html_content: str, base: str) -> str:
        path = f"{base}.html"
        tmp = f"{base}.html.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(html_content)
        os.replace(tmp, path)
        return path

    def _write_json(self, data: ReportData, base: str) -> str:
        path = f"{base}.json"
        tmp = f"{base}.json.tmp"
        summary = _serialise_summary(data)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)
        return path


def _serialise_summary(data: ReportData) -> dict[str, Any]:
    """Machine-readable JSON summary — suitable for dashboards or downstream tools."""
    s = data.summary
    return {
        "generated_at": s.data_generated_at.isoformat(),
        "summary": {
            "total_projects_scored": s.total_projects_scored,
            "total_memos_generated": s.total_memos_generated,
            "flag_for_review_count": s.flag_for_review_count,
            "monitor_count": s.monitor_count,
            "pass_count": s.pass_count,
            "avg_opportunity_score": s.avg_opportunity_score,
            "max_opportunity_score": s.max_opportunity_score,
            "top_district": s.top_district,
            "score_distribution": s.score_distribution.as_dict(),
            "models_used": s.models_used,
        },
        "flag_for_review": [
            {
                "rank": i + 1,
                "project_id": d.memo.project_id,
                "registration_number": d.memo.registration_number,
                "project_name": d.memo.project_name,
                "developer_name": d.memo.developer_name,
                "district": d.project.district,
                "opportunity_score": d.memo.opportunity_score,
                "confidence_score": d.memo.confidence_score,
                "track_record_score": d.memo.track_record_score,
                "construction_progress_pct": d.memo.construction_progress_pct,
                "delay_days": d.memo.delay_days,
                "opportunity_thesis": d.memo.opportunity_thesis,
                "risk_flags": d.memo.risk_flags,
                "data_gaps": d.memo.data_gaps,
            }
            for i, d in enumerate(data.flag_deals)
        ],
        "monitor": [
            {
                "rank": i + 1,
                "project_id": d.memo.project_id,
                "registration_number": d.memo.registration_number,
                "project_name": d.memo.project_name,
                "developer_name": d.memo.developer_name,
                "district": d.project.district,
                "opportunity_score": d.memo.opportunity_score,
                "confidence_score": d.memo.confidence_score,
                "construction_progress_pct": d.memo.construction_progress_pct,
                "delay_days": d.memo.delay_days,
            }
            for i, d in enumerate(data.monitor_deals)
        ],
        "developer_league": [
            {
                "rank": i + 1,
                "developer_name": d.developer_name,
                "promoter_profile_id": d.promoter_profile_id,
                "primary_district": d.primary_district,
                "total_projects": d.total_projects,
                "completed_projects": d.completed_projects,
                "completion_rate": d.completion_rate,
                "on_time_rate": d.on_time_rate,
                "track_record_score": d.track_record_score,
            }
            for i, d in enumerate(data.developer_league)
        ],
    }
