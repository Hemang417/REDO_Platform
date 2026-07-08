"""
Orchestrates the two-tier MAHARERA data collection:

Tier 1 (list pages): Uses HttpClient to fetch HTML, MahareraParser to extract stubs.
Tier 2 (detail API): Uses MahareraApiClient to call JSON endpoints per project.

Responsibilities:
- Pagination loop
- Per-project detail fetching
- Checkpointing (flush to storage every N projects)
- Error isolation (a failed detail fetch does not abort the run)
- Progress logging
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.config.loader import ScraperConfig, StorageConfig
from src.models.raw_project import RawProject
from src.scraper.http_client import HttpClient, ScraperHTTPError
from src.scraper.maharera_api_client import MahareraApiClient, MahareraApiError
from src.scraper.maharera_parser import MahareraParser, build_list_page_params, MMR_PUNE_DISTRICTS
from src.scraper.storage import RawStorage
from src.scraper.document_downloader import DocumentDownloader
from src.scraper.related_entity_fetcher import RelatedEntityFetcher
from src.database.repository import upsert_projects
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger(__name__)

_LIST_URL = "https://maharera.maharashtra.gov.in/projects-search-result"


@dataclass
class CollectionResult:
    run_id: str
    total_fetched: int
    total_failed: int
    output_paths: dict
    duration_seconds: float
    pages_scraped: int

    def __str__(self) -> str:
        return (
            f"CollectionResult(run_id={self.run_id}, "
            f"fetched={self.total_fetched}, failed={self.total_failed}, "
            f"pages={self.pages_scraped}, duration={self.duration_seconds:.1f}s)"
        )


class MahareraCollector:
    """Runs the full MAHARERA collection pipeline.

    Inject all dependencies via the constructor — no module-level state.
    """

    def __init__(
        self,
        http_client: HttpClient,
        api_client: MahareraApiClient,
        parser: MahareraParser,
        storage: RawStorage,
        scraper_config: ScraperConfig,
        db_session_factory: Optional["sessionmaker[Session]"] = None,
        skip_related: bool = False,
        district_ids: Optional[list[int]] = None,
    ) -> None:
        self._http = http_client
        self._api = api_client
        self._parser = parser
        self._storage = storage
        self._cfg = scraper_config
        self._db_session_factory = db_session_factory
        self._skip_related = skip_related
        # [0] = no district filter (all of Maharashtra). Order matters — the
        # first district in the list is the one --start-page applies to when
        # resuming; every subsequent district always starts at page 1.
        self._district_ids = district_ids if district_ids else [0]
        doc_downloader = DocumentDownloader(api_client) if db_session_factory else None
        self._related_fetcher = RelatedEntityFetcher(api_client, doc_downloader)

    def _flush_to_db(self, projects: list[RawProject]) -> None:
        """Upsert newly collected projects into Postgres, if a DB session factory
        was provided. Related entities (documents/professionals/etc.) are fetched
        too unless skip_related=True (fast-pass mode — see scripts/run_backfill.py
        for the separate pass that backfills them afterward)."""
        if not self._db_session_factory or not projects:
            return
        with self._db_session_factory() as session:
            id_by_reg_number = upsert_projects(session, projects)
            if self._skip_related:
                return
            for project in projects:
                db_id = id_by_reg_number.get(project.registration_number)
                if db_id is None:
                    continue
                self._related_fetcher.fetch_and_upsert(
                    session, db_id, project.project_id,
                    project.registration_number, project.promoter_profile_id,
                )

    def collect(self) -> CollectionResult:
        """Run the full collection pipeline across every district in self._district_ids.

        Returns:
            CollectionResult with statistics and output paths.
        """
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        start_time = datetime.now(timezone.utc)
        logger.info("Collection started | run_id=%s", run_id)

        all_projects: list[RawProject] = []
        all_failed: list[dict] = []
        output_paths: dict = {}
        pages_scraped = 0

        try:
            for district_index, district_id in enumerate(self._district_ids):
                district_name = MMR_PUNE_DISTRICTS.get(district_id, "ALL" if district_id == 0 else str(district_id))
                # --start-page only applies to the first district in the list —
                # every subsequent district is a fresh start at page 1.
                start_page = self._cfg.start_page if district_index == 0 else 1

                total_pages = self._determine_total_pages(district_id)

                if self._cfg.end_page is not None and district_index == 0:
                    # User override: trust it; don't cap against an unknown total
                    end_page = (
                        min(self._cfg.end_page, total_pages)
                        if total_pages is not None
                        else self._cfg.end_page
                    )
                else:
                    end_page = total_pages if total_pages is not None else 1

                logger.info(
                    "District %s (id=%d) | scraping pages %d to %d%s",
                    district_name, district_id, start_page, end_page,
                    f" (of {total_pages} total)" if total_pages is not None else " (total unknown)",
                )

                for page_num in range(start_page, end_page + 1):
                    stubs = self._fetch_list_page(page_num, district_id)
                    pages_scraped += 1

                    for stub in stubs:
                        project = self._fetch_detail(stub)
                        if project:
                            all_projects.append(project)
                            self._flush_to_db([project])  # write straight to Postgres as it's scraped
                        else:
                            all_failed.append(stub)

                        # Checkpoint flush
                        if len(all_projects) % self._cfg.checkpoint_interval == 0 and all_projects:
                            logger.info(
                                "Checkpoint | district=%s | page=%d | collected=%d | failed=%d",
                                district_name, page_num, len(all_projects), len(all_failed),
                            )
                            output_paths = self._storage.save(
                                all_projects, run_id, append=(pages_scraped > 1)
                            )

                    if page_num % 10 == 0:
                        logger.info(
                            "Progress | district=%s | page=%d/%d | collected=%d | failed=%d",
                            district_name, page_num, end_page, len(all_projects), len(all_failed),
                        )

        except KeyboardInterrupt:
            logger.warning("Collection interrupted by user. Saving partial results...")
        except MahareraApiError as exc:
            logger.error("API error — likely JWT expiry: %s", exc)
        finally:
            # Final flush of any remaining projects
            if all_projects:
                output_paths = self._storage.save(
                    all_projects, run_id, append=(pages_scraped > 1)
                )
            if all_failed:
                self._storage.save_failed_urls(all_failed, run_id)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        result = CollectionResult(
            run_id=run_id,
            total_fetched=len(all_projects),
            total_failed=len(all_failed),
            output_paths=output_paths,
            duration_seconds=duration,
            pages_scraped=pages_scraped,
        )
        logger.info("Collection complete: %s", result)
        return result

    def _determine_total_pages(self, district_id: int = 0) -> Optional[int]:
        """Fetch page 1 (for the given district filter) to determine how many
        pages exist. Returns None if detection fails."""
        response = self._http.get(_LIST_URL, params=build_list_page_params(1, district_id))
        total = self._parser.extract_total_pages(response.text)
        if total is None:
            logger.warning("Could not determine total pages from pagination HTML.")
            return None
        logger.info("Total pages: %d", total)
        return total

    def _fetch_list_page(self, page_num: int, district_id: int = 0) -> list[dict]:
        """Fetch and parse one list page (optionally filtered to one district).
        Returns a list of project stubs."""
        try:
            # MAHARERA's own pagination is 1-indexed, and requires the full set of
            # search filter params (even empty) alongside `page=` or it silently
            # ignores the page param and always returns page 1.
            response = self._http.get(_LIST_URL, params=build_list_page_params(page_num, district_id))
            stubs = self._parser.parse_list_page(response.text)
            logger.debug("Page %d (district=%d): %d stubs parsed", page_num, district_id, len(stubs))
            return stubs
        except ScraperHTTPError as exc:
            logger.warning("Failed to fetch list page %d (district=%d): %s", page_num, district_id, exc)
            return []

    def _fetch_detail(self, stub: dict) -> Optional[RawProject]:
        """Fetch all detail API endpoints for one project and assemble a RawProject."""
        project_id = stub.get("project_id", "")
        registration_number = stub.get("registration_number", "")

        try:
            general = self._api.get_general_details(project_id)
            if not general:
                logger.debug("No general details for project_id=%s", project_id)
                return self._stub_only_project(stub)

            current_status = self._api.get_current_status(project_id)
            address = self._api.get_land_address(project_id)
            activity = self._api.get_building_activity(project_id)
            extensions = self._api.get_extensions(project_id)
            promoter = self._api.get_promoter_details(project_id)
            litigation = self._api.get_litigation_details(project_id) or {}
            complaints = self._api.get_complaint_details(project_id) or {}

            # Map all API responses to clean field names
            general_fields = self._parser.map_general_details(general)
            status_fields = self._parser.map_current_status(current_status or {})
            address_fields = self._parser.map_address(address)
            promoter_fields = self._parser.map_promoter_details(promoter or {})
            progress = self._parser.compute_construction_progress(activity or {})
            ext_count = self._parser.count_extensions(extensions or [])

            # Extract litigation fields
            is_litigation_present = str(int(bool(litigation.get("isLitigationPresent", False))))
            is_litigation_declared = str(int(bool(litigation.get("isDeclared", False))))
            # Complaint count = sum of complaint types
            complaint_total = (
                len(complaints.get("complaintDetails") or [])
                + len(complaints.get("miscComplaintDetails") or [])
                + len(complaints.get("warrentDetails") or [])
            )
            # isAnyCriminalCases lives in the promoter response
            promoter_raw = promoter or {}
            is_criminal = str(int(bool(promoter_raw.get("isAnyCriminalCases", False))))

            # Prefer the registration number from the API (more reliable)
            reg_num = general_fields.get("registration_number") or registration_number

            return RawProject(
                project_id=project_id,
                registration_number=reg_num,
                project_name=general_fields.get("project_name") or stub.get("project_name", ""),
                developer_name=promoter_fields.get("developer_name") or stub.get("developer_name", ""),
                district=address_fields.get("district") or stub.get("district", ""),
                taluka=address_fields.get("taluka"),
                state=address_fields.get("state"),
                village=address_fields.get("village"),
                project_type=general_fields.get("project_type"),
                status_name=general_fields.get("status_name"),
                current_status=status_fields.get("current_status"),
                is_lapsed=general_fields.get("is_lapsed"),
                is_deregistered=status_fields.get("is_deregistered"),
                is_abeyance=status_fields.get("is_abeyance"),
                proposed_completion_date=general_fields.get("proposed_completion_date"),
                original_completion_date=general_fields.get("original_completion_date"),
                registration_date=general_fields.get("registration_date"),
                construction_progress_pct=progress,
                extension_count=ext_count,
                is_litigation_present=is_litigation_present,
                is_litigation_declared=is_litigation_declared,
                complaint_count=str(complaint_total),
                is_criminal_cases=is_criminal,
                last_modified=stub.get("last_modified"),
                promoter_profile_id=general_fields.get("promoter_profile_id"),
                detail_url=stub.get("detail_url", ""),
                source_url=stub.get("detail_url", ""),
                scraped_at=datetime.now(timezone.utc),
            )

        except MahareraApiError:
            # JWT expired — re-raise to abort the collection run
            raise
        except Exception as exc:
            logger.warning(
                "Failed to build RawProject for project_id=%s registration=%s: %s",
                project_id,
                registration_number,
                exc,
            )
            return None

    def _stub_only_project(self, stub: dict) -> RawProject:
        """Create a minimal RawProject from list-page data only (no detail API data)."""
        return RawProject(
            project_id=stub["project_id"],
            registration_number=stub["registration_number"],
            project_name=stub.get("project_name", ""),
            developer_name=stub.get("developer_name", ""),
            district=stub.get("district", ""),
            last_modified=stub.get("last_modified"),
            detail_url=stub.get("detail_url", ""),
            source_url=stub.get("detail_url", ""),
            scraped_at=datetime.now(timezone.utc),
        )
