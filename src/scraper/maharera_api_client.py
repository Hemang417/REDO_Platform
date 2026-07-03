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
_DMS_DOWNLOAD_URL = (
    "https://maharerait.maharashtra.gov.in"
    "/api/maha-rera-dms-service/batch-job/downloadDocumentForPublicView"
)
_COMPLAINT_API_BASE = "https://maharerait.maharashtra.gov.in/api/maha-rera-complaint-management-service/complaint"
_APPEAL_API_BASE = "https://maharerait.maharashtra.gov.in/api/maha-rera-appeal-service/reatappeal"
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
        """POST to an endpoint on the main project-registration API base."""
        return self._post_absolute(f"{_API_BASE}/{endpoint}", body)

    def _post_absolute(self, url: str, body: dict) -> Optional[dict]:
        """POST to a fully-qualified URL (used for endpoints on other service bases:
        dms-service, complaint-management-service, appeal-service, etc.) and return
        responseObject, or None on failure."""
        time.sleep(self._config.rate_limit_delay)
        try:
            response = self._session.post(
                url,
                json=body,
                timeout=self._config.request_timeout,
            )
        except requests.RequestException as exc:
            raise MahareraApiError(f"Request failed for {url}: {exc}") from exc

        if response.status_code == 401:
            raise MahareraApiError(
                "JWT expired or invalid — re-run scripts/setup_session.py"
            )

        if not response.ok:
            logger.warning(
                "Non-200 from %s | status=%d | body_preview=%.200s",
                url,
                response.status_code,
                response.text,
            )
            return None

        try:
            data = response.json()
            return data.get("responseObject")
        except ValueError as exc:
            logger.warning("JSON parse error for %s: %s", url, exc)
            return None

    def download_document(self, file_name: str, document_id: str) -> Optional[bytes]:
        """Download a document's raw bytes via the DMS service.

        Unlike other endpoints this returns raw binary (e.g. application/pdf),
        not a JSON-wrapped responseObject.
        """
        time.sleep(self._config.rate_limit_delay)
        try:
            response = self._session.post(
                _DMS_DOWNLOAD_URL,
                json={"fileName": file_name, "documentId": document_id},
                timeout=self._config.request_timeout,
            )
        except requests.RequestException as exc:
            raise MahareraApiError(f"Document download failed for {document_id}: {exc}") from exc

        if response.status_code == 401:
            raise MahareraApiError("JWT expired or invalid — re-run scripts/setup_session.py")

        if not response.ok:
            logger.warning(
                "Non-200 downloading document %s (%s) | status=%d",
                document_id, file_name, response.status_code,
            )
            return None

        return response.content

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

    def get_litigation_details(self, project_id: str) -> Optional[dict]:
        """MAHARERA litigation status: isLitigationPresent, isDeclared."""
        return self._post(
            "getProjectLitigationDetails",
            {"projectId": project_id},
        )

    def get_complaint_details(self, project_id: str) -> Optional[dict]:
        """MAHARERA complaint summary: complaintDetails, miscComplaintDetails, warrantDetails."""
        return self._post(
            "getComplaintDetailsByProjectId",
            {"projectId": project_id},
        )

    def get_uploaded_documents(self, project_id: str) -> list:
        """List of uploaded documents for a project: documentDmsRefNo (= the id used
        by download_document), documentFileName, documentTypeId, documentDetails,
        documentDescription, uploadDate, isActive."""
        result = self._post("getUploadedDocuments", {"projectId": project_id})
        return result if isinstance(result, list) else []

    def get_professionals(self, project_id: str) -> list:
        """Project professionals: architects, engineers, CAs, real-estate agents.
        Fields include professionalTypeId, firstName/lastName or entityCompanyName,
        and type-specific registration numbers (architectCoARegistrationNo,
        engineerLicenseNo, caIcaiMembershipNo, realEstateAgentReraRegNo)."""
        result = self._post("getProjectProfessionalByType", {"projectId": project_id})
        return result if isinstance(result, list) else []

    def get_itemized_complaints(self, project_id: str) -> list:
        """Itemized complaints against a project (different from get_complaint_details,
        which only returns aggregate counts). Lives on a separate service base."""
        result = self._post_absolute(
            f"{_COMPLAINT_API_BASE}/getComplaintByProjectId", {"projectId": project_id}
        )
        return result if isinstance(result, list) else []

    def get_appeals(self, project_id: str) -> list:
        """Itemized appeals filed against a project's RERA decisions."""
        result = self._post_absolute(
            f"{_APPEAL_API_BASE}/getAppealDetailsPublicView", {"projectId": project_id}
        )
        return result if isinstance(result, list) else []

    def get_partners(self, project_id: str, user_profile_id: str) -> list:
        """Individual partners/directors/signatories of the promoter entity.
        Requires userProfileId (= promoter_profile_id from general details) in
        addition to projectId — omitting it returns no records even when data exists.
        PII fields (panNumber, mobileNumber, address) come back encrypted by MAHARERA;
        we store them as opaque ciphertext, never attempt to decrypt."""
        result = self._post(
            "fetchPromoterPersonnelContactAddressDetails",
            {"projectId": project_id, "userProfileId": user_profile_id},
        )
        return result if isinstance(result, list) else []

    def get_past_experience(self, project_id: str, user_profile_id: str) -> list:
        """Promoter's past/other project track record: project name, address,
        land area, unit counts, cost, completion dates, litigation flag."""
        result = self._post(
            "getPastExperienceProjectByProjectIdAndUserProfileId",
            {"projectId": project_id, "userProfileId": user_profile_id},
        )
        return result if isinstance(result, list) else []

    def get_spoc(self, project_id: str, user_profile_id: str) -> list:
        """Promoter's single point of contact. Field names unconfirmed — no
        project seen during discovery had a populated record."""
        result = self._post(
            "getPromoterSpocDetails",
            {"projectId": project_id, "userProfileId": user_profile_id},
        )
        return result if isinstance(result, list) else []

    def get_sro_details(self, project_id: str) -> list:
        """Promoter's SRO (professional-body) membership/certificate records.
        Field names unconfirmed for a populated case — no project seen during
        discovery had one, though the {projectId} request shape itself works
        (confirmed via clean 'no records found' response, not an error)."""
        result = self._post("getProjectSroDetails", {"projectId": project_id})
        return result if isinstance(result, list) else []

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "MahareraApiClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
