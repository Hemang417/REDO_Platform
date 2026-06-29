"""Tests for Module 6: report_builder, html_renderer, ReportStorage."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.models.developer_profile import DeveloperProfile
from src.models.investment_memo import InvestmentMemo, RecommendedAction
from src.models.scored_project import ScoredProject
from src.reporting.html_renderer import render_html
from src.reporting.report_builder import build_report, ReportData
from src.reporting.storage import ReportStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_scored(
    project_id: int = 1,
    opportunity_score: float = 55.0,
    district: str = "Pune",
    current_status: str = "Active",
    promoter_profile_id: int = 101,
) -> ScoredProject:
    return ScoredProject(
        project_id=project_id,
        registration_number=f"P{project_id:012d}",
        project_name=f"TEST PROJECT {project_id}",
        developer_name="TEST DEVELOPER",
        district=district,
        current_status=current_status,
        is_lapsed=False,
        is_deregistered=False,
        is_abeyance=False,
        delay_days=400,
        is_delayed=True,
        construction_progress_pct=65.0,
        extension_count=1,
        proposed_completion_date=date(2022, 12, 31),
        opportunity_score=opportunity_score,
        factor_scores={
            "construction_progress": 1.0,
            "delay_severity": 0.8,
            "extension_history": 0.7,
            "project_viability": 1.0,
            "location": 1.0,
        },
        location_tier="tier1",
        detail_url="https://example.com",
        source_url="https://example.com",
        scraped_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        cleaned_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        scored_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        promoter_profile_id=promoter_profile_id,
    )


def _make_memo(
    project_id: int = 1,
    opportunity_score: float = 55.0,
    action: RecommendedAction = RecommendedAction.FLAG_FOR_REVIEW,
) -> InvestmentMemo:
    return InvestmentMemo(
        project_id=project_id,
        registration_number=f"P{project_id:012d}",
        project_name=f"TEST PROJECT {project_id}",
        developer_name="TEST DEVELOPER",
        recommended_action=action,
        opportunity_thesis="Strong construction progress and moderate delay indicate a last-mile funding gap.",
        risk_flags=["Project delayed 400 days.", "Developer on-time rate is 0%."],
        data_gaps=[],
        confidence_score=0.85,
        opportunity_score=opportunity_score,
        track_record_score=62.5,
        construction_progress_pct=65.0,
        delay_days=400,
        extension_count=1,
        model_used="llama-3.3-70b-versatile",
        input_tokens=1000,
        output_tokens=200,
        generated_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )


def _make_developer(promoter_profile_id: int = 101) -> DeveloperProfile:
    return DeveloperProfile(
        promoter_profile_id=promoter_profile_id,
        developer_name="TEST DEVELOPER",
        total_projects=5,
        active_projects=3,
        completed_projects=2,
        lapsed_projects=0,
        deregistered_projects=0,
        abeyance_projects=0,
        completion_rate=0.40,
        on_time_rate=0.60,
        lapse_rate=0.0,
        avg_delay_days=350.0,
        max_delay_days=800,
        avg_extensions=1.2,
        track_record_score=62.5,
        districts=["Pune"],
        primary_district="Pune",
        project_ids=[1],
        computed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )


_WEIGHTS = {
    "construction_progress": 0.30,
    "delay_severity": 0.25,
    "extension_history": 0.15,
    "project_viability": 0.20,
    "location": 0.10,
}


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------

class TestBuildReport:
    def test_returns_report_data(self):
        data = build_report(
            memos=[_make_memo()],
            projects=[_make_scored()],
            developer_profiles=[_make_developer()],
            scoring_weights=_WEIGHTS,
        )
        assert isinstance(data, ReportData)

    def test_flag_deals_populated(self):
        data = build_report(
            memos=[_make_memo(action=RecommendedAction.FLAG_FOR_REVIEW)],
            projects=[_make_scored()],
            developer_profiles=[],
            scoring_weights=_WEIGHTS,
        )
        assert len(data.flag_deals) == 1
        assert len(data.monitor_deals) == 0

    def test_monitor_deals_populated(self):
        data = build_report(
            memos=[_make_memo(action=RecommendedAction.MONITOR)],
            projects=[_make_scored()],
            developer_profiles=[],
            scoring_weights=_WEIGHTS,
        )
        assert len(data.monitor_deals) == 1
        assert len(data.flag_deals) == 0

    def test_deduplication_keeps_higher_score(self):
        # Same project_id, different scores — keep the higher one
        memos = [
            _make_memo(project_id=1, opportunity_score=30.0),
            _make_memo(project_id=1, opportunity_score=55.0),
        ]
        projects = [
            _make_scored(project_id=1, opportunity_score=30.0),
            _make_scored(project_id=1, opportunity_score=55.0),
        ]
        data = build_report(memos=memos, projects=projects, developer_profiles=[], scoring_weights=_WEIGHTS)
        assert len(data.flag_deals) + len(data.monitor_deals) == 1
        all_deals = data.flag_deals + data.monitor_deals
        assert all_deals[0].memo.opportunity_score == 55.0

    def test_developer_joined_to_deal(self):
        data = build_report(
            memos=[_make_memo()],
            projects=[_make_scored(promoter_profile_id=101)],
            developer_profiles=[_make_developer(promoter_profile_id=101)],
            scoring_weights=_WEIGHTS,
        )
        deal = (data.flag_deals + data.monitor_deals)[0]
        assert deal.developer is not None
        assert deal.developer.track_record_score == 62.5

    def test_deals_sorted_by_score_desc(self):
        memos = [
            _make_memo(project_id=1, opportunity_score=20.0, action=RecommendedAction.MONITOR),
            _make_memo(project_id=2, opportunity_score=55.0, action=RecommendedAction.MONITOR),
            _make_memo(project_id=3, opportunity_score=40.0, action=RecommendedAction.MONITOR),
        ]
        projects = [_make_scored(project_id=i) for i in range(1, 4)]
        data = build_report(memos=memos, projects=projects, developer_profiles=[], scoring_weights=_WEIGHTS)
        scores = [d.memo.opportunity_score for d in data.monitor_deals]
        assert scores == sorted(scores, reverse=True)

    def test_summary_counts(self):
        memos = [
            _make_memo(project_id=1, action=RecommendedAction.FLAG_FOR_REVIEW),
            _make_memo(project_id=2, action=RecommendedAction.MONITOR),
            _make_memo(project_id=3, action=RecommendedAction.PASS),
        ]
        projects = [_make_scored(project_id=i) for i in range(1, 4)]
        data = build_report(memos=memos, projects=projects, developer_profiles=[], scoring_weights=_WEIGHTS)
        assert data.summary.flag_for_review_count == 1
        assert data.summary.monitor_count == 1
        assert data.summary.pass_count == 1

    def test_developer_league_sorted_desc(self):
        devs = [
            _make_developer(101),
        ]
        devs[0] = DeveloperProfile(**{**devs[0].model_dump(), "track_record_score": 40.0})
        dev2 = DeveloperProfile(**{**_make_developer(102).model_dump(), "promoter_profile_id": 102, "track_record_score": 80.0})
        data = build_report(memos=[], projects=[], developer_profiles=[devs[0], dev2], scoring_weights=_WEIGHTS)
        assert data.developer_league[0].track_record_score == 80.0

    def test_empty_input_produces_valid_report(self):
        data = build_report(memos=[], projects=[], developer_profiles=[], scoring_weights=_WEIGHTS)
        assert data.summary.total_memos_generated == 0
        assert data.flag_deals == []
        assert data.monitor_deals == []


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------

class TestRenderHtml:
    def _make_data(self) -> ReportData:
        return build_report(
            memos=[
                _make_memo(project_id=1, action=RecommendedAction.FLAG_FOR_REVIEW),
                _make_memo(project_id=2, action=RecommendedAction.MONITOR),
            ],
            projects=[_make_scored(project_id=1), _make_scored(project_id=2)],
            developer_profiles=[_make_developer()],
            scoring_weights=_WEIGHTS,
        )

    def test_returns_html_string(self):
        html = render_html(self._make_data())
        assert isinstance(html, str)
        assert html.startswith("<!DOCTYPE html>")

    def test_contains_report_title(self):
        html = render_html(self._make_data())
        assert "Deal Origination Report" in html

    def test_contains_project_name(self):
        html = render_html(self._make_data())
        assert "TEST PROJECT 1" in html

    def test_contains_opportunity_score(self):
        html = render_html(self._make_data())
        assert "55.0" in html

    def test_contains_developer_name(self):
        html = render_html(self._make_data())
        assert "TEST DEVELOPER" in html

    def test_flag_section_present(self):
        html = render_html(self._make_data())
        assert "Flag for Review" in html

    def test_monitor_section_present(self):
        html = render_html(self._make_data())
        assert "Monitor" in html

    def test_methodology_section_present(self):
        html = render_html(self._make_data())
        assert "Methodology" in html

    def test_scoring_weights_shown(self):
        html = render_html(self._make_data())
        assert "30%" in html  # construction_progress weight

    def test_no_raw_html_injection(self):
        # Ensure user-supplied strings are escaped
        from dataclasses import replace
        memo = _make_memo()
        memo = InvestmentMemo(**{
            **memo.model_dump(),
            "project_name": "<script>alert('xss')</script>",
            "generated_at": memo.generated_at,
        })
        data = build_report(memos=[memo], projects=[_make_scored()], developer_profiles=[], scoring_weights=_WEIGHTS)
        html = render_html(data)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_empty_data_renders_without_error(self):
        data = build_report(memos=[], projects=[], developer_profiles=[], scoring_weights=_WEIGHTS)
        html = render_html(data)
        assert "<!DOCTYPE html>" in html


# ---------------------------------------------------------------------------
# ReportStorage
# ---------------------------------------------------------------------------

class TestReportStorage:
    def _make_data(self) -> ReportData:
        return build_report(
            memos=[_make_memo()],
            projects=[_make_scored()],
            developer_profiles=[_make_developer()],
            scoring_weights=_WEIGHTS,
        )

    def test_writes_html_file(self):
        data = self._make_data()
        html = render_html(data)
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReportStorage(tmp)
            paths = storage.save(data, html, run_id="20240601_120000")
            assert "html" in paths
            assert Path(paths["html"]).exists()

    def test_writes_json_file(self):
        data = self._make_data()
        html = render_html(data)
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReportStorage(tmp)
            paths = storage.save(data, html, run_id="20240601_120000")
            assert "json" in paths
            assert Path(paths["json"]).exists()

    def test_json_is_valid(self):
        data = self._make_data()
        html = render_html(data)
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReportStorage(tmp)
            paths = storage.save(data, html, run_id="20240601_120000")
            with open(paths["json"], encoding="utf-8") as fh:
                summary = json.load(fh)
            assert "summary" in summary
            assert "flag_for_review" in summary
            assert "monitor" in summary
            assert "developer_league" in summary

    def test_json_summary_counts_correct(self):
        memos = [
            _make_memo(project_id=1, action=RecommendedAction.FLAG_FOR_REVIEW),
            _make_memo(project_id=2, action=RecommendedAction.MONITOR),
        ]
        data = build_report(
            memos=memos,
            projects=[_make_scored(project_id=1), _make_scored(project_id=2)],
            developer_profiles=[],
            scoring_weights=_WEIGHTS,
        )
        html = render_html(data)
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReportStorage(tmp)
            paths = storage.save(data, html, run_id="20240601_120000")
            with open(paths["json"], encoding="utf-8") as fh:
                summary = json.load(fh)
            assert summary["summary"]["flag_for_review_count"] == 1
            assert summary["summary"]["monitor_count"] == 1
            assert len(summary["flag_for_review"]) == 1
            assert len(summary["monitor"]) == 1

    def test_html_content_written_correctly(self):
        data = self._make_data()
        html = render_html(data)
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReportStorage(tmp)
            paths = storage.save(data, html, run_id="20240601_120000")
            written = Path(paths["html"]).read_text(encoding="utf-8")
            assert "TEST PROJECT 1" in written
            assert "<!DOCTYPE html>" in written

    def test_creates_output_directory(self):
        data = self._make_data()
        html = render_html(data)
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "nested", "reports")
            storage = ReportStorage(new_dir)
            paths = storage.save(data, html, run_id="20240601_120000")
            assert Path(paths["html"]).exists()

    def test_run_id_in_filename(self):
        data = self._make_data()
        html = render_html(data)
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReportStorage(tmp)
            paths = storage.save(data, html, run_id="TESTRUN")
            assert "TESTRUN" in paths["html"]
            assert "TESTRUN" in paths["json"]
