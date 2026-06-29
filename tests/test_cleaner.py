"""Tests for Module 2: field parsers and MahareraCleaner."""

from datetime import date, datetime, timezone

import pytest

from src.cleaner.field_parsers import (
    compute_delay_days,
    normalise_location,
    normalise_name,
    parse_bool,
    parse_date,
    parse_float,
    parse_int,
)
from src.cleaner.maharera_cleaner import MahareraCleaner
from src.config.loader import CleanerConfig
from src.models.raw_project import RawProject

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S")

_CLEANER_CONFIG = CleanerConfig(
    raw_input_dir="output/raw",
    clean_output_dir="output/clean",
    json_enabled=True,
    csv_enabled=True,
    date_formats=_DATE_FORMATS,
)


def _make_raw(**overrides) -> RawProject:
    defaults = dict(
        project_id="42",
        registration_number="P52700000042",
        project_name="  TEST  TOWERS  ",
        developer_name="MANOJ  AWASTHI",
        district="pune",
        taluka="Haveli",
        state="MAHARASHTRA",
        village="Hadapsar",
        project_type="Residential / Group Housing",
        status_name="Ongoing",
        current_status="Active",
        is_lapsed="0",
        is_deregistered="0",
        is_abeyance="0",
        proposed_completion_date="2024-12-31",
        original_completion_date="2023-12-31",
        registration_date="2020-06-01",
        construction_progress_pct="67.5",
        extension_count="2",
        last_modified="2024-01-01",
        promoter_profile_id="99999",
        detail_url="https://maharerait.maharashtra.gov.in/public/project/view/42",
        source_url="https://maharerait.maharashtra.gov.in/public/project/view/42",
        scraped_at=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RawProject(**defaults)


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_iso_format(self):
        assert parse_date("2024-12-31", _DATE_FORMATS) == date(2024, 12, 31)

    def test_dmy_slash(self):
        assert parse_date("31/12/2024", _DATE_FORMATS) == date(2024, 12, 31)

    def test_dmy_dash(self):
        assert parse_date("31-12-2024", _DATE_FORMATS) == date(2024, 12, 31)

    def test_datetime_string_strips_time(self):
        assert parse_date("2024-12-31T00:00:00", _DATE_FORMATS) == date(2024, 12, 31)

    def test_none_returns_none(self):
        assert parse_date(None, _DATE_FORMATS) is None

    def test_empty_returns_none(self):
        assert parse_date("", _DATE_FORMATS) is None

    def test_garbage_returns_none(self):
        assert parse_date("not-a-date", _DATE_FORMATS) is None


# ---------------------------------------------------------------------------
# parse_float
# ---------------------------------------------------------------------------

class TestParseFloat:
    def test_simple_float(self):
        assert parse_float("67.5") == 67.5

    def test_integer_string(self):
        assert parse_float("100") == 100.0

    def test_strips_percent_sign(self):
        assert parse_float("67.5%") == 67.5

    def test_clamps_to_max(self):
        assert parse_float("150.0", max_val=100.0) == 100.0

    def test_clamps_to_min(self):
        assert parse_float("-5.0", min_val=0.0) == 0.0

    def test_none_returns_none(self):
        assert parse_float(None) is None

    def test_garbage_returns_none(self):
        assert parse_float("N/A") is None


# ---------------------------------------------------------------------------
# parse_int
# ---------------------------------------------------------------------------

class TestParseInt:
    def test_numeric_string(self):
        assert parse_int("42") == 42

    def test_zero(self):
        assert parse_int("0") == 0

    def test_none_returns_none(self):
        assert parse_int(None) is None

    def test_float_string_fails(self):
        assert parse_int("1.5") is None


# ---------------------------------------------------------------------------
# parse_bool
# ---------------------------------------------------------------------------

class TestParseBool:
    def test_one_is_true(self):
        assert parse_bool("1") is True

    def test_zero_is_false(self):
        assert parse_bool("0") is False

    def test_true_string(self):
        assert parse_bool("true") is True

    def test_false_string(self):
        assert parse_bool("false") is False

    def test_none_returns_none(self):
        assert parse_bool(None) is None

    def test_garbage_returns_none(self):
        assert parse_bool("maybe") is None


# ---------------------------------------------------------------------------
# normalise_name
# ---------------------------------------------------------------------------

class TestNormaliseName:
    def test_uppercases(self):
        assert normalise_name("test towers") == "TEST TOWERS"

    def test_collapses_whitespace(self):
        assert normalise_name("MANOJ  AWASTHI") == "MANOJ AWASTHI"

    def test_strips_edges(self):
        assert normalise_name("  TEST  ") == "TEST"

    def test_none_returns_empty(self):
        assert normalise_name(None) == ""

    def test_empty_returns_empty(self):
        assert normalise_name("") == ""


# ---------------------------------------------------------------------------
# normalise_location
# ---------------------------------------------------------------------------

class TestNormaliseLocation:
    def test_title_cases(self):
        assert normalise_location("PUNE") == "Pune"

    def test_strips(self):
        assert normalise_location("  Thane  ") == "Thane"

    def test_none_returns_none(self):
        assert normalise_location(None) is None

    def test_empty_returns_none(self):
        assert normalise_location("") is None


# ---------------------------------------------------------------------------
# compute_delay_days
# ---------------------------------------------------------------------------

class TestComputeDelayDays:
    def test_overdue(self):
        result = compute_delay_days(date(2020, 1, 1), reference=date(2024, 1, 1))
        assert result == 1461  # 4 years including one leap year

    def test_ahead_of_schedule(self):
        result = compute_delay_days(date(2030, 1, 1), reference=date(2024, 1, 1))
        assert result is not None and result < 0

    def test_none_proposed_returns_none(self):
        assert compute_delay_days(None) is None


# ---------------------------------------------------------------------------
# MahareraCleaner
# ---------------------------------------------------------------------------

class TestMahareraCleaner:
    def setup_method(self):
        self.cleaner = MahareraCleaner(_CLEANER_CONFIG)

    def test_clean_returns_clean_project(self):
        raw = _make_raw()
        result = self.cleaner.clean(raw)
        assert result is not None

    def test_project_id_is_int(self):
        result = self.cleaner.clean(_make_raw())
        assert isinstance(result.project_id, int)
        assert result.project_id == 42

    def test_developer_name_normalised(self):
        result = self.cleaner.clean(_make_raw())
        assert result.developer_name == "MANOJ AWASTHI"

    def test_project_name_normalised(self):
        result = self.cleaner.clean(_make_raw())
        assert result.project_name == "TEST TOWERS"

    def test_district_title_cased(self):
        result = self.cleaner.clean(_make_raw())
        assert result.district == "Pune"

    def test_dates_are_date_objects(self):
        result = self.cleaner.clean(_make_raw())
        assert isinstance(result.proposed_completion_date, date)
        assert result.proposed_completion_date == date(2024, 12, 31)

    def test_progress_is_float(self):
        result = self.cleaner.clean(_make_raw())
        assert isinstance(result.construction_progress_pct, float)
        assert result.construction_progress_pct == 67.5

    def test_extension_count_is_int(self):
        result = self.cleaner.clean(_make_raw())
        assert isinstance(result.extension_count, int)
        assert result.extension_count == 2

    def test_bool_flags_are_bools(self):
        result = self.cleaner.clean(_make_raw())
        assert result.is_lapsed is False
        assert result.is_deregistered is False

    def test_delay_days_computed(self):
        result = self.cleaner.clean(_make_raw(proposed_completion_date="2020-01-01"))
        assert result.delay_days is not None
        assert result.delay_days > 0
        assert result.is_delayed is True

    def test_future_project_not_delayed(self):
        result = self.cleaner.clean(_make_raw(proposed_completion_date="2099-12-31"))
        assert result.is_delayed is False

    def test_invalid_project_id_returns_none(self):
        result = self.cleaner.clean(_make_raw(project_id="not-a-number"))
        assert result is None

    def test_null_fields_become_none(self):
        result = self.cleaner.clean(_make_raw(taluka=None, village=None))
        assert result.taluka is None
        assert result.village is None

    def test_clean_batch_counts(self):
        raws = [_make_raw(project_id=str(i)) for i in range(1, 6)]
        raws.append(_make_raw(project_id="bad"))
        cleaned, failed = self.cleaner.clean_batch(raws)
        assert len(cleaned) == 5
        assert len(failed) == 1
