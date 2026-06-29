"""
Typed wrappers around MAHARERA's internal JSON API.

All endpoints are POST with Content-Type: application/json.
Authentication: Bearer JWT in Authorization header.

Single responsibility: make authenticated API calls and return raw response objects.
No parsing, no business logic, no storage.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config.loader import ScraperConfig

logger = logging.getLogger(__name__)

_API_BASE = (
    "https://maharerait.maharashtra.gov.in"
    "/api/maha-rera-public-view-project-registration-service"
    "/public/projectregistartion"  # typo is intentional: this is MAHARERA's API path
)
_AUTH_URL = (
    "https://maharerait.maharashtra.gov.in"
    "/api/maha-rera-login-service/login/authenticatePublic"
)
_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)


class MahareraApiError(Exception):
    """Raised when an API call fails after all retries."""


class MahareraApiClient:
    """Makes authenticated POST calls to MAHARERA's project detail API.

    Usage:
        client = MahareraApiClient(jwt_token, config.scraper)
        with client:
            general = client.get_general_details("100")
    """

    def __init__(self, jwt_token: str, config: ScraperConfig) -> None:
        self._jwt = jwt_token
        self._config = config
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": self._config.user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "https://maharerait.maharashtra.gov.in/",
                "Origin": "https://maharerait.maharashtra.gov.in",
                "Authorization": f"Bearer {self._jwt}",
            }
        )
        retry = Retry(
            total=self._config.max_retries,
            backoff_factor=self._config.retry_backoff_factor,
            status_forcelist=_RETRY_STATUS_CODES,
            allowed_methods=["POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        return session

    def _post(self, endpoint: str, body: dict) -> Optional[dict]:
        """POST to an API endpoint and return responseObject, or None on failure."""
        time.sleep(self._config.rate_limit_delay)
        url = f"{_API_BASE}/{endpoint}"
        try:
            response = self._session.post(
                url,
                json=body,
                timeout=self._config.request_timeout,
            )
        except requests.RequestException as exc:
            raise MahareraApiError(f"Request failed for {endpoint}: {exc}") from exc

        if response.status_code == 401:
            raise MahareraApiError(
                "JWT expired or invalid — re-run scripts/setup_session.py"
            )

        if not response.ok:
            logger.warning(
                "Non-200 from %s | status=%d | body_preview=%.200s",
                endpoint,
                response.status_code,
                response.text,
            )
            return None

        try:
            data = response.json()
            return data.get("responseObject")
        except ValueError as exc:
            logger.warning("JSON parse error for %s: %s", endpoint, exc)
            return None

    # ------------------------------------------------------------------
    # Endpoint wrappers — one method per API endpoint we use
    # ------------------------------------------------------------------

    def get_general_details(self, project_id: str) -> Optional[dict]:
        """Project name, type, status, completion dates, registration number."""
        return self._post(
            "getProjectGeneralDetailsByProjectId",
            {"projectId": project_id},
        )

    def get_current_status(self, project_id: str) -> Optional[dict]:
        """Current project status (Active/Completed/Lapsed/Deregistered)."""
        return self._post(
            "getProjectCurrentStatus",
            {"projectId": project_id},
        )

    def get_land_address(self, project_id: str) -> Optional[dict]:
        """District, taluka, state, village."""
        return self._post(
            "getProjectLandAddressDetails",
            {"projectId": project_id},
        )

    def get_building_activity(self, project_id: str) -> Optional[dict]:
        """Per-activity completion percentages (used to compute overall progress)."""
        return self._post(
            "getBuildingWingsActivityDetails",
            {"projectId": project_id},
        )

    def get_extensions(self, project_id: str) -> Optional[list]:
        """List of prior extension records."""
        result = self._post(
            "getProjectPreviousExtensionDetails",
            {"projectId": project_id},
        )
        return result if isinstance(result, list) else []

    def get_promoter_details(self, project_id: str) -> Optional[dict]:
        """Developer/promoter name and identifiers."""
        return self._post(
            "getProjectAndAssociatedPromoterDetails",
            {"projectId": project_id},
        )

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "MahareraApiClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
