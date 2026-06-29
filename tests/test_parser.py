"""Tests for MahareraParser — HTML parsing and API field mapping."""

import os
import pytest
from unittest.mock import patch

from src.scraper.maharera_parser import MahareraParser


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(filename: str) -> str:
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# List page parsing
# ---------------------------------------------------------------------------

class TestParseListPage:
    def test_parses_ten_cards(self):
        html = _load_fixture("sample_list_page.html")
        parser = MahareraParser()
        stubs = parser.parse_list_page(html)
        assert len(stubs) == 10, f"Expected 10 cards, got {len(stubs)}"

    def test_stub_has_required_keys(self):
        html = _load_fixture("sample_list_page.html")
        parser = MahareraParser()
        stubs = parser.parse_list_page(html)
        required_keys = {"registration_number", "project_name", "developer_name",
                         "district", "last_modified", "detail_url", "project_id"}
        for stub in stubs:
            assert required_keys.issubset(set(stub.keys())), f"Missing keys in stub: {stub}"

    def test_registration_number_format(self):
        html = _load_fixture("sample_list_page.html")
        parser = MahareraParser()
        stubs = parser.parse_list_page(html)
        for stub in stubs:
            reg = stub["registration_number"]
            assert reg.startswith("P"), f"Unexpected reg number format: {reg}"
            assert len(reg) >= 5

    def test_detail_url_is_absolute(self):
        html = _load_fixture("sample_list_page.html")
        parser = MahareraParser()
        stubs = parser.parse_list_page(html)
        for stub in stubs:
            url = stub["detail_url"]
            assert url.startswith("https://"), f"Detail URL not absolute: {url}"

    def test_project_id_is_numeric(self):
        html = _load_fixture("sample_list_page.html")
        parser = MahareraParser()
        stubs = parser.parse_list_page(html)
        for stub in stubs:
            assert stub["project_id"].isdigit(), f"Non-numeric project_id: {stub['project_id']}"

    def test_empty_html_returns_empty_list(self):
        parser = MahareraParser()
        result = parser.parse_list_page("<html><body></body></html>")
        assert result == []


# ---------------------------------------------------------------------------
# Total page extraction
# ---------------------------------------------------------------------------

class TestExtractTotalPages:
    def test_extracts_from_fixture(self):
        html = _load_fixture("sample_list_page.html")
        parser = MahareraParser()
        total = parser.extract_total_pages(html)
        # Either a number or None (if fixture has no pagination)
        assert total is None or (isinstance(total, int) and total > 0)


# ---------------------------------------------------------------------------
# API field mapping
# ---------------------------------------------------------------------------

class TestMapGeneralDetails:
    def test_maps_known_fields(self):
        parser = MahareraParser()
        api_response = {
            "projectRegistartionNo": "P52700000123",
            "projectName": "TEST TOWERS",
            "projectTypeName": "Residential / Group Housing",
            "projectStatusName": "Ongoing",
            "projectProposeComplitionDate": "2026-03-31",
            "originalProjectProposeCompletionDate": "2025-12-31",
            "reraRegistrationDate": "2022-01-15",
            "isProjectLapsed": 0,
            "userProfileId": 99999,
        }
        result = parser.map_general_details(api_response)
        assert result["registration_number"] == "P52700000123"
        assert result["project_name"] == "TEST TOWERS"
        assert result["project_type"] == "Residential / Group Housing"
        assert result["status_name"] == "Ongoing"
        assert result["is_lapsed"] == "0"

    def test_missing_fields_return_none(self):
        parser = MahareraParser()
        result = parser.map_general_details({})
        assert result["registration_number"] is None
        assert result["project_name"] is None


class TestMapCurrentStatus:
    def test_maps_core_status(self):
        parser = MahareraParser()
        api_response = {
            "coreStatus": {
                "statusName": "Active",
                "isDeregistered": 0,
                "isAbeyance": 0,
            }
        }
        result = parser.map_current_status(api_response)
        assert result["current_status"] == "Active"
        assert result["is_deregistered"] == "0"


class TestMapAddress:
    def test_maps_list_response(self):
        parser = MahareraParser()
        api_response = [
            {"districtName": "Pune", "talukaName": "Haveli", "stateName": "MAHARASHTRA", "villageName": "Hadapsar"}
        ]
        result = parser.map_address(api_response)
        assert result["district"] == "Pune"
        assert result["taluka"] == "Haveli"

    def test_maps_dict_response(self):
        parser = MahareraParser()
        api_response = {"districtName": "Mumbai", "talukaName": "Borivali", "stateName": "MAHARASHTRA"}
        result = parser.map_address(api_response)
        assert result["district"] == "Mumbai"


class TestComputeConstructionProgress:
    def test_computes_average(self):
        parser = MahareraParser()
        api_response = {
            "projectActivityDetails": [
                {
                    "activities": [
                        {"completionPercentage": 100.0},
                        {"completionPercentage": 80.0},
                        {"completionPercentage": 60.0},
                    ]
                }
            ]
        }
        result = parser.compute_construction_progress(api_response)
        assert result == "80.0"

    def test_returns_none_for_empty(self):
        parser = MahareraParser()
        assert parser.compute_construction_progress({}) is None
        assert parser.compute_construction_progress(None) is None

    def test_handles_multiple_wings(self):
        parser = MahareraParser()
        api_response = {
            "projectActivityDetails": [
                {"activities": [{"completionPercentage": 100.0}]},
                {"activities": [{"completionPercentage": 0.0}]},
            ]
        }
        result = parser.compute_construction_progress(api_response)
        assert result == "50.0"


class TestCountExtensions:
    def test_counts_list(self):
        parser = MahareraParser()
        assert parser.count_extensions([{}, {}, {}]) == "3"
        assert parser.count_extensions([]) == "0"

    def test_handles_non_list(self):
        parser = MahareraParser()
        assert parser.count_extensions(None) == "0"
