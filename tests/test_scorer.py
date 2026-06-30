"""Tests for Module 3: scoring rules and MahareraScorer."""

from datetime import date, datetime, timezone

import pytest

from src.config.loader import (
    ConstructionProgressConfig,
    DelayConfig,
    ExtensionConfig,
    HardFilterConfig,
    LocationConfig,
    ScoringConfig,
    ScoringWeights,
    ViabilityConfig,
    load_scoring_config,
)
from src.models.clean_project import CleanProject
from src.scorer.maharera_scorer import MahareraScorer
from src.scorer.rules import (
    score_construction_progress,
    score_delay_severity,
    score_extension_history,
    score_location,
    score_project_viability,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_WEIGHTS = ScoringWeights(
    construction_progress=0.30,
    delay_severity=0.25,
    extension_history=0.15,
    project_viability=0.20,
    location=0.10,
)

_CP_CFG = ConstructionProgressConfig(
    optimal_min=40.0, optimal_max=85.0,
    score_below_optimal=0.50, score_in_optimal=1.00,
    score_above_optimal=0.40, score_complete=0.10,
)

_DELAY_CFG = DelayConfig(
    no_delay_score=0.20,
    moderate_delay_min_days=180, moderate_delay_max_days=730, moderate_delay_score=1.00,
    severe_delay_max_days=1095, severe_delay_score=0.60,
    extreme_delay_score=0.15,
)

_EXT_CFG = ExtensionConfig(
    scores=((0, 0.30), (1, 0.80), (2, 1.00), (3, 0.50)),
    four_plus_score=0.20,
)

_VIA_CFG = ViabilityConfig(
    active_score=1.00, completed_score=0.20,
    lapsed_score=0.00, deregistered_score=0.00,
    abeyance_score=0.10, unknown_score=0.50,
)

_LOC_CFG = LocationConfig(
    tier1_districts=("Mumbai", "Mumbai Suburban", "Thane", "Pune", "Navi Mumbai"),
    tier2_districts=("Nagpur", "Nashik", "Aurangabad"),
    tier1_score=1.00, tier2_score=0.65, other_score=0.35,
)

_HARD_FILTER_CFG = HardFilterConfig(
    construction_progress_min=0.0,
    construction_progress_max=100.0,
    exclude_lapsed=True,
    exclude_deregistered=True,
    exclude_abeyance=False,
    exclude_if_litigation=False,
    exclude_if_criminal_cases=False,
)

_SCORING_CFG = ScoringConfig(
    weights=_WEIGHTS,
    construction_progress=_CP_CFG,
    delay_severity=_DELAY_CFG,
    extension_history=_EXT_CFG,
    project_viability=_VIA_CFG,
    location=_LOC_CFG,
    hard_filters=_HARD_FILTER_CFG,
)


def _make_clean(**overrides) -> CleanProject:
    defaults = dict(
        project_id=1,
        registration_number="P52700000001",
        project_name="TEST TOWERS",
        developer_name="TEST DEVELOPER",
        district="Pune",
        construction_progress_pct=65.0,
        delay_days=400,
        extension_count=1,
        current_status="Active",
        is_lapsed=False,
        is_deregistered=False,
        is_abeyance=False,
        proposed_completion_date=date(2024, 6, 1),
        detail_url="https://example.com",
        source_url="https://example.com",
        scraped_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        cleaned_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        is_delayed=True,
    )
    defaults.update(overrides)
    return CleanProject(**defaults)


# ---------------------------------------------------------------------------
# score_construction_progress
# ---------------------------------------------------------------------------

class TestScoreConstructionProgress:
    def test_in_optimal_range(self):
        assert score_construction_progress(65.0, _CP_CFG) == 1.00

    def test_below_optimal(self):
        assert score_construction_progress(30.0, _CP_CFG) == 0.50

    def test_above_optimal(self):
        assert score_construction_progress(90.0, _CP_CFG) == 0.40

    def test_complete(self):
        assert score_construction_progress(100.0, _CP_CFG) == 0.10

    def test_none_is_neutral(self):
        assert score_construction_progress(None, _CP_CFG) == 0.5

    def test_optimal_boundary_min(self):
        assert score_construction_progress(40.0, _CP_CFG) == 1.00

    def test_optimal_boundary_max(self):
        assert score_construction_progress(85.0, _CP_CFG) == 1.00


# ---------------------------------------------------------------------------
# score_delay_severity
# ---------------------------------------------------------------------------

class TestScoreDelaySeverity:
    def test_no_delay(self):
        assert score_delay_severity(0, _DELAY_CFG) == 0.20

    def test_ahead_of_schedule(self):
        assert score_delay_severity(-30, _DELAY_CFG) == 0.20

    def test_moderate_delay(self):
        assert score_delay_severity(365, _DELAY_CFG) == 1.00

    def test_severe_delay(self):
        assert score_delay_severity(900, _DELAY_CFG) == 0.60

    def test_extreme_delay(self):
        assert score_delay_severity(1500, _DELAY_CFG) == 0.15

    def test_none_is_neutral(self):
        assert score_delay_severity(None, _DELAY_CFG) == 0.5

    def test_boundary_moderate_min(self):
        assert score_delay_severity(180, _DELAY_CFG) == 1.00

    def test_boundary_moderate_max(self):
        assert score_delay_severity(730, _DELAY_CFG) == 1.00


# ---------------------------------------------------------------------------
# score_extension_history
# ---------------------------------------------------------------------------

class TestScoreExtensionHistory:
    def test_zero_extensions(self):
        assert score_extension_history(0, _EXT_CFG) == 0.30

    def test_one_extension(self):
        assert score_extension_history(1, _EXT_CFG) == 0.80

    def test_two_extensions(self):
        assert score_extension_history(2, _EXT_CFG) == 1.00

    def test_three_extensions(self):
        assert score_extension_history(3, _EXT_CFG) == 0.50

    def test_four_plus(self):
        assert score_extension_history(5, _EXT_CFG) == 0.20


# ---------------------------------------------------------------------------
# score_project_viability
# ---------------------------------------------------------------------------

class TestScoreProjectViability:
    def test_active_project(self):
        s = score_project_viability("Active", False, False, False, _VIA_CFG)
        assert s == 1.00

    def test_lapsed_flag_is_hard_zero(self):
        s = score_project_viability("Active", True, False, False, _VIA_CFG)
        assert s == 0.00

    def test_deregistered_flag(self):
        s = score_project_viability("Active", False, True, False, _VIA_CFG)
        assert s == 0.00

    def test_abeyance_flag(self):
        s = score_project_viability("Active", False, False, True, _VIA_CFG)
        assert s == 0.10

    def test_completed_status_string(self):
        s = score_project_viability("Completed", False, False, False, _VIA_CFG)
        assert s == 0.20

    def test_unknown_status(self):
        s = score_project_viability(None, False, False, False, _VIA_CFG)
        assert s == 0.50

    def test_lapsed_string_when_flag_false(self):
        s = score_project_viability("Lapsed", False, False, False, _VIA_CFG)
        assert s == 0.00


# ---------------------------------------------------------------------------
# score_location
# ---------------------------------------------------------------------------

class TestScoreLocation:
    def test_tier1_district(self):
        score, tier = score_location("Pune", _LOC_CFG)
        assert score == 1.00
        assert tier == "tier1"

    def test_tier2_district(self):
        score, tier = score_location("Nagpur", _LOC_CFG)
        assert score == 0.65
        assert tier == "tier2"

    def test_other_district(self):
        score, tier = score_location("Beed", _LOC_CFG)
        assert score == 0.35
        assert tier == "other"

    def test_case_insensitive(self):
        score, _ = score_location("pune", _LOC_CFG)
        assert score == 1.00


# ---------------------------------------------------------------------------
# MahareraScorer end-to-end
# ---------------------------------------------------------------------------

class TestMahareraScorer:
    def setup_method(self):
        self.scorer = MahareraScorer(_SCORING_CFG)

    def test_score_returns_scored_project(self):
        result = self.scorer.score(_make_clean())
        assert result is not None
        assert 0.0 <= result.opportunity_score <= 100.0

    def test_factor_scores_present(self):
        result = self.scorer.score(_make_clean())
        expected_keys = {
            "construction_progress", "delay_severity",
            "extension_history", "project_viability", "location",
        }
        assert set(result.factor_scores.keys()) == expected_keys

    def test_all_factor_scores_bounded(self):
        result = self.scorer.score(_make_clean())
        for name, score in result.factor_scores.items():
            assert 0.0 <= score <= 1.0, f"Factor {name} out of bounds: {score}"

    def test_lapsed_project_scores_low(self):
        lapsed = _make_clean(is_lapsed=True, current_status="Lapsed")
        result = self.scorer.score(lapsed)
        assert result.opportunity_score < 30.0

    def test_ideal_project_scores_high(self):
        # 65% progress, 365-day delay, 2 extensions, active, Pune
        ideal = _make_clean(
            construction_progress_pct=65.0,
            delay_days=365,
            extension_count=2,
            current_status="Active",
            is_lapsed=False,
            district="Pune",
        )
        result = self.scorer.score(ideal)
        assert result.opportunity_score > 70.0

    def test_location_tier_stored(self):
        result = self.scorer.score(_make_clean(district="Pune"))
        assert result.location_tier == "tier1"

    def test_score_batch_returns_correct_count(self):
        projects = [_make_clean(project_id=i, registration_number=f"P{i:012d}") for i in range(1, 6)]
        results = self.scorer.score_batch(projects)
        assert len(results) == 5

    def test_original_fields_preserved(self):
        project = _make_clean()
        result = self.scorer.score(project)
        assert result.project_id == project.project_id
        assert result.registration_number == project.registration_number


# ---------------------------------------------------------------------------
# load_scoring_config integration
# ---------------------------------------------------------------------------

class TestLoadScoringConfig:
    def test_loads_from_file(self):
        config = load_scoring_config("config/scoring_rules.yaml")
        assert config.weights.construction_progress == 0.30
        assert "Pune" in config.location.tier1_districts
        assert config.delay_severity.moderate_delay_min_days == 180

    def test_weights_sum_to_one(self):
        config = load_scoring_config("config/scoring_rules.yaml")
        w = config.weights
        total = (
            w.construction_progress + w.delay_severity
            + w.extension_history + w.project_viability + w.location
        )
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, not 1.0"
