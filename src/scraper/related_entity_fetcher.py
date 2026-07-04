"""
Fetches and upserts a project's "expensive" related entities: documents,
professionals, itemized complaints, appeals, partners, past-experience,
SPOC, and SRO details.

Extracted from MahareraCollector so it can be reused by both:
- The live collector (when NOT running in fast/skip-related mode)
- scripts/run_backfill.py, which re-runs this for already-scraped projects
  without needing to re-walk the list pages.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from src.scraper.maharera_api_client import MahareraApiClient, MahareraApiError
from src.scraper.document_downloader import DocumentDownloader
from src.database.repository import (
    upsert_documents,
    upsert_professionals,
    upsert_complaints,
    upsert_appeals,
    upsert_partners,
    upsert_past_experiences,
    upsert_spocs,
    upsert_sro_details,
    ProfessionalRecord,
    ComplaintRecord,
    AppealRecord,
    PartnerRecord,
    PastExperienceRecord,
    SpocRecord,
    SroDetailRecord,
)

logger = logging.getLogger(__name__)


def _to_str(value: object) -> Optional[str]:
    """Coerce a JSON value (int/float/bool/None/str) to str for String columns,
    without the '1.0' float-formatting surprises str() gives for whole floats."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class RelatedEntityFetcher:
    """Fetches and upserts one project's documents/professionals/complaints/
    appeals/partners/past-experience/SPOC/SRO records.

    Failures here are logged and swallowed (except JWT expiry, which re-raises)
    so a related-entity hiccup never loses the already-upserted Project row.
    """

    def __init__(self, api_client: MahareraApiClient, doc_downloader: Optional[DocumentDownloader]) -> None:
        self._api = api_client
        self._doc_downloader = doc_downloader

    def fetch_and_upsert(
        self,
        session: Session,
        db_id: int,
        project_id: str,
        registration_number: str,
        promoter_profile_id: Optional[str],
    ) -> None:
        reg_num = registration_number
        try:
            if self._doc_downloader:
                documents = self._doc_downloader.download_for_project(db_id, project_id, reg_num)
                upsert_documents(session, documents)

            professionals_raw = self._api.get_professionals(project_id)
            professionals = [
                ProfessionalRecord(
                    project_id=db_id,
                    registration_number=reg_num,
                    promoter_professional_id=p.get("promoterProfessionalId"),
                    professional_type_id=p.get("professionalTypeId"),
                    first_name=p.get("firstName"),
                    last_name=p.get("lastName"),
                    entity_company_name=p.get("entityCompanyName"),
                    architect_coa_registration_no=p.get("architectCoARegistrationNo"),
                    engineer_license_no=p.get("engineerLicenseNo"),
                    ca_icai_membership_no=p.get("caIcaiMembershipNo"),
                    real_estate_agent_rera_reg_no=p.get("realEstateAgentReraRegNo"),
                )
                for p in professionals_raw
                if p.get("promoterProfessionalId") is not None
            ]
            upsert_professionals(session, professionals)

            complaints_raw = self._api.get_itemized_complaints(project_id)
            complaints = [
                ComplaintRecord(
                    project_id=db_id,
                    registration_number=reg_num,
                    complaint_no=str(
                        c.get("complaintRegistrationNo") or c.get("complaintId") or f"unknown-{i}"
                    ),
                    complaint_date=c.get("complaintRegistrationDate"),
                    complainant_name=c.get("profileNameComplainant"),
                    respondent_name=c.get("profileNameRespondent"),
                    complaint_status=c.get("complaintStatus"),
                    raw_data=c,
                )
                for i, c in enumerate(complaints_raw)
            ]
            upsert_complaints(session, complaints)

            appeals_raw = self._api.get_appeals(project_id)
            appeals = [
                AppealRecord(
                    project_id=db_id,
                    registration_number=reg_num,
                    appeal_no=str(a.get("appealNo") or a.get("appealNumber") or f"unknown-{i}"),
                    complaint_reference_no=a.get("complaintReferenceNo") or a.get("referenceNo"),
                    appeal_date=a.get("appealDate"),
                    appellant_name=a.get("appellantName"),
                    respondent_name=a.get("respondentName"),
                    appeal_status=a.get("appealStatus") or a.get("status"),
                    raw_data=a,
                )
                for i, a in enumerate(appeals_raw)
            ]
            upsert_appeals(session, appeals)

            # Partners, past experience, and SPOC all require the promoter's
            # userProfileId (= promoter_profile_id) in addition to projectId.
            if promoter_profile_id:
                partners_raw = self._api.get_partners(project_id, promoter_profile_id)
                partners = [
                    PartnerRecord(
                        project_id=db_id,
                        registration_number=reg_num,
                        personnel_id=p["userProfilePesonnelContactAddressDetailsId"],
                        first_name=p.get("firstname"),
                        middle_name=p.get("middleName"),
                        last_name=p.get("lastName"),
                        designation=p.get("userProfilePersonnelDesignationId"),
                        pan_number_encrypted=p.get("panNumber"),
                        mobile_number_encrypted=p.get("mobileNumber"),
                        email_hash=p.get("emailId"),
                        din_number=p.get("dinNumber"),
                        raw_data=p,
                    )
                    for p in partners_raw
                    if p.get("userProfilePesonnelContactAddressDetailsId") is not None
                ]
                upsert_partners(session, partners)

                past_exp_raw = self._api.get_past_experience(project_id, promoter_profile_id)
                past_experiences = [
                    PastExperienceRecord(
                        project_id=db_id,
                        registration_number=reg_num,
                        past_experience_id=pe["userProfilePastExperienceId"],
                        past_project_name=pe.get("projectName"),
                        address=pe.get("address"),
                        land_area=_to_str(pe.get("landArea")),
                        number_of_buildings_plots=_to_str(pe.get("numberOfBuildingsPlots")),
                        number_of_apartments=_to_str(pe.get("numberOfApartments")),
                        total_cost=_to_str(pe.get("totalCost")),
                        original_proposed_completion_date=pe.get("originalProposedCompletionDate"),
                        actual_completion_date=pe.get("actualCompletionDate"),
                        past_project_type_name=pe.get("projectTypeName"),
                        past_project_status=_to_str(pe.get("projectStatusId")),
                        is_project_has_litigation=_to_str(pe.get("isProjectHasLitigation")),
                        is_registered_with_maharera=_to_str(pe.get("isProjectsRegisteredWithMahaRERA")),
                        maharera_registration_number=pe.get("mahaRERARegistrationNumber"),
                        raw_data=pe,
                    )
                    for pe in past_exp_raw
                    if pe.get("userProfilePastExperienceId") is not None
                ]
                upsert_past_experiences(session, past_experiences)

                spoc_raw = self._api.get_spoc(project_id, promoter_profile_id)
                spocs = [
                    SpocRecord(
                        project_id=db_id,
                        registration_number=reg_num,
                        spoc_id=str(s.get("promoterSpocDetailsId") or f"unknown-{i}"),
                        first_name=s.get("firstName"),
                        middle_name=s.get("middleName"),
                        last_name=s.get("lastName"),
                        designation=s.get("designation"),
                        spoc_type=s.get("spocType"),
                        mobile_number=s.get("mobileNumber"),
                        email=s.get("emailId"),
                        pan_number=s.get("panNumber"),
                        raw_data=s,
                    )
                    for i, s in enumerate(spoc_raw)
                ]
                upsert_spocs(session, spocs)

            sro_raw = self._api.get_sro_details(project_id)
            sro_details = [
                SroDetailRecord(
                    project_id=db_id,
                    registration_number=reg_num,
                    sro_id=str(s.get("id") or s.get("sroId") or f"unknown-{i}"),
                    raw_data=s,
                )
                for i, s in enumerate(sro_raw)
            ]
            upsert_sro_details(session, sro_details)

        except MahareraApiError:
            raise
        except Exception as exc:
            logger.warning(
                "Failed to fetch/upsert related entities for project_id=%s registration=%s: %s",
                project_id, reg_num, exc,
            )
