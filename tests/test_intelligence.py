"""Tests for Module 4: DeveloperAggregator and track record scoring."""

from datetime import date, datetime, timezone

import pytest

from src.config.loader import (
    DevPortfolioThreshold,
    DevThreshold,
    DevWeights,
    DeveloperScoringConfig,
    load_developer_scoring_config,
)
from src.intelligence.developer_aggregator import (
    DeveloperAggregator,
    _linear_interpolate,
    _score_portfolio_size,
)
from src.models.scored_project import ScoredProject

# ---------------------------------------------------------------------------
# Config fixture
# ---------------------------------------------------------------------------

_DEV_CFG = DeveloperScoringConfig(
    weights=DevWeights(
        completion_rate=0.35,
        on_time_rate=0.30,
        no_lapse_rate=0.20,
        portfolio_size=0.15,
    ),
    completion_rate=DevThreshold(excellent_threshold=0.80, poor_threshold=0.30),
    on_time_rate=DevThreshold(excellent_threshold=0.70, poor_threshold=0.10),
    no_lapse_rate=DevThreshold(excellent_threshold=0.95, poor_threshold=0.60),
    portfolio_size=DevPortfolioThreshold(large_threshold=10, small_threshold=1, single_score=0.30),
)


def _make_scored(
    project_id: int = 1,
    developer_name: str = "GOOD DEVELOPER",
    promoter_profile_id: int = 101,
    district: str = "Pune",
    current_status: str = "Active",
    is_lapsed: bool = False,
    is_deregistered: bool = False,
    is_abeyance: bool = False,
    delay_days: int = 400,
    construction_progress_pct: float = 65.0,
    extension_count: int = 1,
    opportunity_score: float = 55.0,
) -> ScoredProject:
    return ScoredProject(
        project_id=project_id,
        registration_number=f"P{project_id:012d}",
        project_name="TEST PROJECT",
        developer_name=developer_name,
        district=district,
        current_status=current_status,
        is_lapsed=is_lapsed,
        is_deregistered=is_deregistered,
        is_abeyance=is_abeyance,
        delay_days=delay_days,
        is_delayed=delay_days > 0,
        construction_progress_pct=construction_progress_pct,
        extension_count=extension_count,
        proposed_completion_date=date(2022, 12, 31),
        opportunity_score=opportunity_score,
        factor_scores={
            "construction_progress": 1.0,
            "delay_severity": 1.0,
            "extension_history": 0.8,
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


# ---------------------------------------------------------------------------
# _linear_interpolate
# ---------------------------------------------------------------------------

class TestLinearInterpolate:
    def test_at_excellent(self):
        assert _linear_interpolate(0.80, poor=0.30, excellent=0.80) == 1.0

    def test_at_poor(self):
        assert _linear_interpolate(0.30, poor=0.30, excellent=0.80) == 0.0

    def test_midpoint(self):
        result = _linear_interpolate(0.55, poor=0.30, excellent=0.80)
        assert abs(result - 0.5) < 1e-9

    def test_clamped_above(self):
        assert _linear_interpolate(1.0, poor=0.30, excellent=0.80) == 1.0

    def test_clamped_below(self):
        assert _linear_interpolate(0.0, poor=0.30, excellent=0.80) == 0.0


# ---------------------------------------------------------------------------
# _score_portfolio_size
# ---------------------------------------------------------------------------

class TestScorePortfolioSize:
    def test_single_project(self):
        assert _score_portfolio_size(1, _DEV_CFG.portfolio_size) == 0.30

    def test_large_portfolio(self):
        assert _score_portfolio_size(10, _DEV_CFG.portfolio_size) == 1.0

    def test_over_large(self):
        assert _score_portfolio_size(20, _DEV_CFG.portfolio_size) == 1.0

    def test_mid_range(self):
        result = _score_portfolio_size(5, _DEV_CFG.portfolio_size)
        assert 0.30 < result < 1.0


# ---------------------------------------------------------------------------
# DeveloperAggregator grouping
# ---------------------------------------------------------------------------

class TestGrouping:
    def setup_method(self):
        self.agg = DeveloperAggregator(_DEV_CFG)

    def test_groups_by_profile_id(self):
        projects = [
            _make_scored(project_id=1, promoter_profile_id=101),
            _make_scored(project_id=2, promoter_profile_id=101),
            _make_scored(project_id=3, promoter_profile_id=202),
        ]
        profiles = self.agg.aggregate(projects)
        assert len(profiles) == 2

    def test_groups_by_name_when_no_profile_id(self):
        projects = [
            _make_scored(project_id=1, promoter_profile_id=None, developer_name="DEV A"),
            _make_scored(project_id=2, promoter_profile_id=None, developer_name="DEV A"),
            _make_scored(project_id=3, promoter_profile_id=None, developer_name="DEV B"),
        ]
        profiles = self.agg.aggregate(projects)
        assert len(profiles) == 2

    def test_profile_id_stored(self):
        projects = [_make_scored(promoter_profile_id=999)]
        profiles = self.agg.aggregate(projects)
        assert profiles[0].promoter_profile_id == 999

    def test_project_ids_collected(self):
        projects = [
            _make_scored(project_id=10, promoter_profile_id=101),
            _make_scored(project_id=20, promoter_profile_id=101),
        ]
        profiles = self.agg.aggregate(projects)
        assert sorted(profiles[0].project_ids) == [10, 20]


# ---------------------------------------------------------------------------
# DeveloperAggregator metrics
# ---------------------------------------------------------------------------

class TestMetrics:
    def setup_method(self):
        self.agg = DeveloperAggregator(_DEV_CFG)

    def test_total_projects(self):
        projects = [_make_scored(project_id=i, promoter_profile_id=1) for i in range(5)]
        profile = self.agg.aggregate(projects)[0]
        assert profile.total_projects == 5

    def test_completed_count(self):
        projects = [
            _make_scored(project_id=1, promoter_profile_id=1, current_status="Completed"),
            _make_scored(project_id=2, promoter_profile_id=1, current_status="Completed"),
            _make_scored(project_id=3, promoter_profile_id=1, current_status="Active"),
        ]
        profile = self.agg.aggregate(projects)[0]
        assert profile.completed_projects == 2

    def test_lapsed_count(self):
        projects = [
            _make_scored(project_id=1, promoter_profile_id=1, is_lapsed=True),
            _make_scored(project_id=2, promoter_profile_id=1, is_lapsed=False),
        ]
        profile = self.agg.aggregate(projects)[0]
        assert profile.lapsed_projects == 1
        assert abs(profile.lapse_rate - 0.5) < 1e-9

    def test_on_time_rate(self):
        projects = [
            _make_scored(project_id=1, promoter_profile_id=1, delay_days=-10),
            _make_scored(project_id=2, promoter_profile_id=1, delay_days=-5),
            _make_scored(project_id=3, promoter_profile_id=1, delay_days=300),
            _make_scored(project_id=4, promoter_profile_id=1, delay_days=600),
        ]
        profile = self.agg.aggregate(projects)[0]
        assert profile.on_time_rate == 0.5

    def test_avg_delay(self):
        projects = [
            _make_scored(project_id=1, promoter_profile_id=1, delay_days=200),
            _make_scored(project_id=2, promoter_profile_id=1, delay_days=400),
        ]
        profile = self.agg.aggregate(projects)[0]
        assert profile.avg_delay_days == 300.0

    def test_primary_district(self):
        projects = [
            _make_scored(project_id=1, promoter_profile_id=1, district="Pune"),
            _make_scored(project_id=2, promoter_profile_id=1, district="Pune"),
            _make_scored(project_id=3, promoter_profile_id=1, district="Thane"),
        ]
        profile = self.agg.aggregate(projects)[0]
        assert profile.primary_district == "Pune"

    def test_districts_sorted(self):
        projects = [
            _make_scored(project_id=1, promoter_profile_id=1, district="Thane"),
            _make_scored(project_id=2, promoter_profile_id=1, district="Pune"),
        ]
        profile = self.agg.aggregate(projects)[0]
        assert profile.districts == ["Pune", "Thane"]

    def test_avg_opportunity_score(self):
        projects = [
            _make_scored(project_id=1, promoter_profile_id=1, opportunity_score=60.0),
            _make_scored(project_id=2, promoter_profile_id=1, opportunity_score=80.0),
        ]
        profile = self.agg.aggregate(projects)[0]
        assert profile.avg_opportunity_score == 70.0
        assert profile.max_opportunity_score == 80.0


# ---------------------------------------------------------------------------
# Track record score
# ---------------------------------------------------------------------------

class TestTrackRecordScore:
    def setup_method(self):
        self.agg = DeveloperAggregator(_DEV_CFG)

    def test_score_is_in_range(self):
        profile = self.agg.aggregate([_make_scored()])[0]
        assert 0.0 <= profile.track_record_score <= 100.0

    def test_excellent_developer_scores_high(self):
        # All projects completed on-time, no lapsed, large portfolio
        projects = [
            _make_scored(
                project_id=i, promoter_profile_id=1,
                current_status="Completed",
                delay_days=-10,
                is_lapsed=False,
            )
            for i in range(10)
        ]
        profile = self.agg.aggregate(projects)[0]
        assert profile.track_record_score > 70.0

    def test_poor_developer_scores_low(self):
        projects = [
            _make_scored(
                project_id=i, promoter_profile_id=1,
                current_status="Lapsed",
                is_lapsed=True,
                delay_days=2000,
            )
            for i in range(5)
        ]
        profile = self.agg.aggregate(projects)[0]
        assert profile.track_record_score < 30.0

    def test_sorted_descending(self):
        good_projects = [
            _make_scored(project_id=i, promoter_profile_id=1,
                         current_status="Completed", delay_days=-5, is_lapsed=False)
            for i in range(10)
        ]
        bad_projects = [
            _make_scored(project_id=i + 100, promoter_profile_id=2, developer_name="BAD DEV",
                         current_status="Lapsed", is_lapsed=True, delay_days=2000)
            for i in range(3)
        ]
        profiles = self.agg.aggregate(good_projects + bad_projects)
        scores = [p.track_record_score for p in profiles]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# load_developer_scoring_config integration
# ---------------------------------------------------------------------------

class TestLoadDeveloperScoringConfig:
    def test_loads_from_file(self):
        cfg = load_developer_scoring_config("config/scoring_rules.yaml")
        assert cfg.weights.completion_rate == 0.35
        assert cfg.completion_rate.excellent_threshold == 0.80
        assert cfg.portfolio_size.large_threshold == 10

    def test_weights_sum_to_one(self):
        cfg = load_developer_scoring_config("config/scoring_rules.yaml")
        w = cfg.weights
        total = w.completion_rate + w.on_time_rate + w.no_lapse_rate + w.portfolio_size
        assert abs(total - 1.0) < 1e-9
