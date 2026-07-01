"""
Parses raw HTML from MAHARERA list pages into stub dicts.
Also contains the API response mapper for detail data (JSON → raw dict).

Single responsibility: data extraction and field mapping only.
No HTTP calls, no file I/O, no business logic.

CSS selectors are named constants at the top of this file.
When MAHARERA changes their markup, this is the only place to update.
"""

from __future__ import annotations

import logging
import re
from statistics import mean
from typing import Optional

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSS selector constants — update here if MAHARERA changes their HTML
# ---------------------------------------------------------------------------
_CARD_SELECTOR = "div.row.shadow.p-3.mb-5.bg-body.rounded"
_REG_NUMBER_SELECTOR = ".col-xl-4 > p.p-0"
_PROJECT_NAME_SELECTOR = ".col-xl-4 h4.title4"
_DEVELOPER_NAME_SELECTOR = ".col-xl-4 p.darkBlue.bold"
_DETAIL_URL_SELECTOR = ".col-xl-2 a.click-projectmodal.viewLink"

# Within the info columns (col-xl-6 area)
_LABEL_SELECTOR = ".col-xl-6 .greyColor"

# Pagination (site markup as of 2026-07: div.customPagination div.pagination,
# e.g. `Pages <span class="pagesCount" data-total="48747">1</span>of 4875`)
_PAGINATION_SELECTOR = "div.customPagination div.pagination"
_PAGE_QUERY_PARAM = "page"

# Fixed query params the site requires alongside `page=` — omitting these
# causes the site to silently ignore `page=` and always return page 1.
LIST_PAGE_FIXED_PARAMS = {
    "project_name": "",
    "project_location": "",
    "project_completion_date": "",
    "project_state": 27,  # Maharashtra
    "project_district": 0,
    "carpetAreas": "",
    "completionPercentages": "",
    "project_division": "",
    "op": "",
}

# Detail subdomain
_DETAIL_SUBDOMAIN = "https://maharerait.maharashtra.gov.in"

# ---------------------------------------------------------------------------
# API field mappings — MAHARERA has typos; we map to clean names here
# ---------------------------------------------------------------------------
# getProjectGeneralDetailsByProjectId
_GENERAL_FIELDS = {
    "projectRegistartionNo": "registration_number",       # typo: "registartion"
    "projectName": "project_name",
    "projectTypeName": "project_type",
    "projectStatusName": "status_name",
    "projectProposeComplitionDate": "proposed_completion_date",  # typo: "complition"
    "originalProjectProposeCompletionDate": "original_completion_date",
    "reraRegistrationDate": "registration_date",
    "isProjectLapsed": "is_lapsed",
    "userProfileId": "promoter_profile_id",
}

# getProjectCurrentStatus → responseObject.coreStatus
_STATUS_FIELDS = {
    "statusName": "current_status",
    "isDeregistered": "is_deregistered",
    "isAbeyance": "is_abeyance",
}

# getProjectLandAddressDetails → responseObject[0]
_ADDRESS_FIELDS = {
    "districtName": "district",
    "talukaName": "taluka",
    "stateName": "state",
    "villageName": "village",
}

# getProjectAndAssociatedPromoterDetails → responseObject.promoterDetails
_PROMOTER_FIELDS = {
    "promoterName": "developer_name",
}


class MahareraParser:
    """Parses MAHARERA list-page HTML and maps API JSON responses to raw dicts.

    All methods are pure — they accept bytes/dicts and return dicts.
    No external calls are made.
    """

    # ------------------------------------------------------------------
    # List page HTML parsing
    # ------------------------------------------------------------------

    def parse_list_page(self, html: str) -> list[dict[str, str]]:
        """Extract project stubs from a list-page HTML string.

        Args:
            html: Raw HTML content of a MAHARERA project search results page.

        Returns:
            List of stub dicts with: registration_number, project_name,
            developer_name, district, last_modified, detail_url.
        """
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(_CARD_SELECTOR)

        if not cards:
            logger.warning("No project cards found on page — selector may need updating")
            return []

        stubs: list[dict[str, str]] = []
        for card in cards:
            stub = self._parse_card(card)
            if stub:
                stubs.append(stub)

        logger.debug("Parsed %d project stubs from list page", len(stubs))
        return stubs

    def _parse_card(self, card: Tag) -> Optional[dict[str, str]]:
        """Extract fields from a single project card."""
        try:
            reg_el = card.select_one(_REG_NUMBER_SELECTOR)
            reg_number = reg_el.get_text(strip=True).lstrip("# ") if reg_el else None

            name_el = card.select_one(_PROJECT_NAME_SELECTOR)
            project_name = name_el.get_text(strip=True) if name_el else None

            dev_el = card.select_one(_DEVELOPER_NAME_SELECTOR)
            developer_name = dev_el.get_text(strip=True) if dev_el else None

            # District and last_modified are inside the grey-label columns
            district = self._extract_labelled_value(card, "District")
            last_modified = self._extract_labelled_value(card, "Last Modified")

            detail_el = card.select_one(_DETAIL_URL_SELECTOR)
            detail_url = detail_el.get("href", "") if detail_el else None
            if detail_url and detail_url.startswith("/"):
                detail_url = f"{_DETAIL_SUBDOMAIN}{detail_url}"

            # Extract numeric project ID from detail URL
            project_id = None
            if detail_url:
                match = re.search(r"/view/(\d+)", detail_url)
                if match:
                    project_id = match.group(1)

            if not reg_number or not project_id:
                logger.debug("Skipping card: missing registration number or detail URL")
                return None

            return {
                "registration_number": reg_number,
                "project_name": project_name or "",
                "developer_name": developer_name or "",
                "district": district or "",
                "last_modified": last_modified or "",
                "detail_url": detail_url or "",
                "project_id": project_id,
            }
        except Exception as exc:
            logger.warning("Failed to parse card: %s", exc)
            return None

    def _extract_labelled_value(self, card: Tag, label: str) -> Optional[str]:
        """Find a value next to a grey label div matching `label`."""
        for grey_div in card.select(".greyColor"):
            if grey_div.get_text(strip=True) == label:
                value_el = grey_div.find_next_sibling("p")
                if value_el:
                    return value_el.get_text(strip=True)
        return None

    def extract_total_pages(self, html: str) -> Optional[int]:
        """Extract total page count from the list page pagination.

        Site markup: `Pages <span class="pagesCount" data-total="48747">1</span>of 4875`
        — page numbering is 1-indexed.
        """
        soup = BeautifulSoup(html, "lxml")

        pagination = soup.select_one(_PAGINATION_SELECTOR)
        if pagination:
            text = pagination.get_text(" ", strip=True)
            match = re.search(r"of\s+(\d+)", text)
            if match:
                return int(match.group(1))

        logger.warning("Could not determine total pages from HTML")
        return None

    # ------------------------------------------------------------------
    # API JSON response mapping
    # ------------------------------------------------------------------

    def map_general_details(self, response_object: dict) -> dict[str, Optional[str]]:
        """Map getProjectGeneralDetailsByProjectId responseObject to clean fields."""
        result = {}
        for api_key, clean_key in _GENERAL_FIELDS.items():
            val = response_object.get(api_key)
            result[clean_key] = str(val) if val is not None else None
        return result

    def map_current_status(self, response_object: dict) -> dict[str, Optional[str]]:
        """Map getProjectCurrentStatus responseObject to clean fields."""
        result = {}
        core = response_object.get("coreStatus", {}) if isinstance(response_object, dict) else {}
        for api_key, clean_key in _STATUS_FIELDS.items():
            val = core.get(api_key)
            result[clean_key] = str(val) if val is not None else None
        return result

    def map_address(self, response_object) -> dict[str, Optional[str]]:
        """Map getProjectLandAddressDetails responseObject to clean fields."""
        item = (response_object[0] if isinstance(response_object, list) and response_object
                else response_object or {})
        result = {}
        for api_key, clean_key in _ADDRESS_FIELDS.items():
            val = item.get(api_key) if isinstance(item, dict) else None
            result[clean_key] = str(val) if val is not None else None
        return result

    def map_promoter_details(self, response_object: dict) -> dict[str, Optional[str]]:
        """Map getProjectAndAssociatedPromoterDetails promoterDetails to clean fields."""
        promoter = (response_object.get("promoterDetails", {})
                    if isinstance(response_object, dict) else {})
        result = {}
        for api_key, clean_key in _PROMOTER_FIELDS.items():
            val = promoter.get(api_key)
            result[clean_key] = str(val) if val is not None else None
        return result

    def compute_construction_progress(self, response_object: dict) -> Optional[str]:
        """Compute average construction completion % from building activity response.

        MAHARERA reports per-activity percentages (Excavation, Plinth, etc.).
        We return the mean across all available activities as the overall progress.

        Args:
            response_object: responseObject from getBuildingWingsActivityDetails.

        Returns:
            String representation of percentage (e.g., "67.5") or None.
        """
        if not isinstance(response_object, dict):
            return None

        activity_details = response_object.get("projectActivityDetails", [])
        if not isinstance(activity_details, list):
            return None

        percentages: list[float] = []
        for wing in activity_details:
            activities = wing.get("activities", []) if isinstance(wing, dict) else []
            for act in activities:
                if isinstance(act, dict):
                    pct = act.get("completionPercentage")
                    if pct is not None:
                        try:
                            percentages.append(float(pct))
                        except (TypeError, ValueError):
                            pass

        if not percentages:
            return None

        avg = mean(percentages)
        return f"{avg:.1f}"

    def count_extensions(self, response_object) -> str:
        """Count prior extension records for a project."""
        if isinstance(response_object, list):
            return str(len(response_object))
        return "0"
