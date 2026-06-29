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
from src.scraper.maharera_parser import MahareraParser
from src.scraper.storage import RawStorage

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
    ) -> None:
        self._http = http_client
        self._api = api_client
        self._parser = parser
        self._storage = storage
        self._cfg = scraper_config

    def collect(self) -> CollectionResult:
        """Run the full collection pipeline.

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
            total_pages = self._determine_total_pages()

            if self._cfg.end_page is not None:
                # User override: trust it; don't cap against an unknown total
                end_page = (
                    min(self._cfg.end_page, total_pages)
                    if total_pages is not None
                    else self._cfg.end_page
                )
            else:
                end_page = total_pages if total_pages is not None else 1

            logger.info(
                "Scraping pages %d to %d%s",
                self._cfg.start_page,
                end_page,
                f" (of {total_pages} total)" if total_pages is not None else " (total unknown)",
            )

            for page_num in range(self._cfg.start_page, end_page + 1):
                stubs = self._fetch_list_page(page_num)
                pages_scraped += 1

                for stub in stubs:
                    project = self._fetch_detail(stub)
                    if project:
                        all_projects.append(project)
                    else:
                        all_failed.append(stub)

                    # Checkpoint flush
                    if len(all_projects) % self._cfg.checkpoint_interval == 0 and all_projects:
                        logger.info(
                            "Checkpoint | page=%d | collected=%d | failed=%d",
                            page_num,
                            len(all_projects),
                            len(all_failed),
                        )
                        output_paths = self._storage.save(
                            all_projects, run_id, append=(pages_scraped > 1)
                        )

                if page_num % 10 == 0:
                    logger.info(
                        "Progress | page=%d/%d | collected=%d | failed=%d",
                        page_num,
                        end_page,
                        len(all_projects),
                        len(all_failed),
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

    def _determine_total_pages(self) -> Optional[int]:
        """Fetch page 1 to determine how many pages exist. Returns None if detection fails."""
        response = self._http.get(_LIST_URL, params={"page": 0})
        total = self._parser.extract_total_pages(response.text)
        if total is None:
            logger.warning("Could not determine total pages from pagination HTML.")
            return None
        logger.info("Total pages: %d", total)
        return total

    def _fetch_list_page(self, page_num: int) -> list[dict]:
        """Fetch and parse one list page. Returns a list of project stubs."""
        try:
            # MAHARERA uses 0-indexed pages in the query param
            response = self._http.get(
                _LIST_URL, params={"page": page_num - 1}
            )
            stubs = self._parser.parse_list_page(response.text)
            logger.debug("Page %d: %d stubs parsed", page_num, len(stubs))
            return stubs
        except ScraperHTTPError as exc:
            logger.warning("Failed to fetch list page %d: %s", page_num, exc)
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

            # Map all API responses to clean field names
            general_fields = self._parser.map_general_details(general)
            status_fields = self._parser.map_current_status(current_status or {})
            address_fields = self._parser.map_address(address)
            promoter_fields = self._parser.map_promoter_details(promoter or {})
            progress = self._parser.compute_construction_progress(activity or {})
            ext_count = self._parser.count_extensions(extensions or [])

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
