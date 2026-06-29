"""Tests for RawStorage — JSON and CSV output."""

import csv
import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

from src.config.loader import StorageConfig
from src.models.raw_project import RawProject
from src.scraper.storage import RawStorage


def _make_project(project_id: str = "1", reg: str = "P52700000001") -> RawProject:
    return RawProject(
        project_id=project_id,
        registration_number=reg,
        project_name="TEST PROJECT",
        developer_name="TEST DEVELOPER",
        district="Pune",
        taluka="Haveli",
        state="MAHARASHTRA",
        project_type="Residential / Group Housing",
        status_name="Ongoing",
        current_status="Active",
        is_lapsed="0",
        is_deregistered="0",
        is_abeyance="0",
        proposed_completion_date="2026-12-31",
        original_completion_date="2025-12-31",
        registration_date="2022-01-15",
        construction_progress_pct="67.5",
        extension_count="1",
        last_modified="2024-03-01",
        promoter_profile_id="99999",
        detail_url="https://maharerait.maharashtra.gov.in/public/project/view/1",
        source_url="https://maharerait.maharashtra.gov.in/public/project/view/1",
        scraped_at=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
    )


def _make_storage(tmp_dir: str, json_enabled=True, csv_enabled=True) -> RawStorage:
    config = StorageConfig(
        raw_output_dir=tmp_dir,
        json_enabled=json_enabled,
        csv_enabled=csv_enabled,
    )
    return RawStorage(config)


class TestJsonOutput:
    def test_creates_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            projects = [_make_project()]
            paths = storage.save(projects, "20240601_100000")
            assert "json" in paths
            assert os.path.exists(paths["json"])

    def test_json_is_valid_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            projects = [_make_project("1"), _make_project("2", "P52700000002")]
            paths = storage.save(projects, "20240601_100000")
            with open(paths["json"], encoding="utf-8") as fh:
                data = json.load(fh)

        assert isinstance(data, list)
        assert len(data) == 2

    def test_json_contains_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            paths = storage.save([_make_project()], "20240601_100000")
            with open(paths["json"], encoding="utf-8") as fh:
                data = json.load(fh)

        record = data[0]
        assert record["registration_number"] == "P52700000001"
        assert record["district"] == "Pune"
        assert record["construction_progress_pct"] == "67.5"

    def test_append_mode_accumulates(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            storage.save([_make_project("1")], "run1", append=False)
            storage.save([_make_project("2", "P52700000002")], "run1", append=True)
            json_path = os.path.join(tmp, "maharera_projects_run1.json")
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)

        assert len(data) == 2

    def test_atomic_write_no_tmp_file_remaining(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            storage.save([_make_project()], "20240601_100000")
            tmp_files = [f for f in os.listdir(tmp) if f.endswith(".tmp")]
        assert len(tmp_files) == 0


class TestCsvOutput:
    def test_creates_csv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            paths = storage.save([_make_project()], "20240601_100000")
            assert "csv" in paths
            assert os.path.exists(paths["csv"])

    def test_csv_has_header_and_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            paths = storage.save([_make_project()], "20240601_100000")
            with open(paths["csv"], encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["registration_number"] == "P52700000001"
        assert rows[0]["district"] == "Pune"

    def test_csv_has_all_required_columns(self):
        from src.scraper.storage import _CSV_FIELDS
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            paths = storage.save([_make_project()], "20240601_100000")
            with open(paths["csv"], encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                headers = reader.fieldnames

        for field in _CSV_FIELDS:
            assert field in headers, f"Missing CSV column: {field}"


class TestDisabledFormats:
    def test_json_disabled_produces_no_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp, json_enabled=False)
            paths = storage.save([_make_project()], "run1")
        assert "json" not in paths

    def test_csv_disabled_produces_no_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp, csv_enabled=False)
            paths = storage.save([_make_project()], "run1")
        assert "csv" not in paths


class TestEmptyInput:
    def test_empty_list_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            result = storage.save([], "run1")
        assert result == {}
