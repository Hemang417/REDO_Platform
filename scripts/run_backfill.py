"""
Backfill pass: fetches documents/professionals/complaints/appeals/partners/
past-experience/SPOC/SRO for projects that already have a core `projects` row
in Postgres (e.g. scraped via `run_collector.py --skip-related`).

Unlike run_collector.py, this does NOT re-walk the MAHARERA list pages —
it reads project_id/registration_number/promoter_profile_id directly from
Postgres, so it can resume cleanly by primary key (`--start-id`) without any
dependency on page numbers.

Prerequisites:
    A valid JWT (run scripts/setup_session.py first) and a Postgres
    connection with an already-populated `projects` table.

Usage:
    python scripts/run_backfill.py
    python scripts/run_backfill.py --start-id 500     # resume after project id 500
    python scripts/run_backfill.py --limit 50         # test run, first 50 projects only
    python scripts/run_backfill.py --setup            # force a new CAPTCHA session

Exit codes:
    0  Backfill completed (possibly with some per-project failures, logged)
    1  Fatal error (JWT expired before starting, config/DB missing, etc.)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.config.loader import load_config
from src.scraper.browser_client import load_token, setup_session, SessionSetupError
from src.scraper.maharera_api_client import MahareraApiClient, MahareraApiError
from src.scraper.document_downloader import DocumentDownloader
from src.scraper.related_entity_fetcher import RelatedEntityFetcher
from src.database.session import get_session_factory, init_db
from src.database.models import Project
from src.utils.logger import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill documents/professionals/complaints/appeals/partners/"
                    "past-experience/SPOC/SRO for already-scraped MAHARERA projects."
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to settings YAML file (default: config/settings.yaml)",
    )
    parser.add_argument(
        "--start-id",
        type=int,
        default=0,
        help="Resume after this Project.id (DB primary key). Default 0 = start from the beginning.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after this many projects (for a quick test run).",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Force a new CAPTCHA session setup even if a token already exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = load_config(args.config)
    setup_logging(config.logging)
    logger = logging.getLogger(__name__)

    jwt = None
    if not args.setup:
        jwt = load_token()

    if not jwt:
        logger.info("No valid token found. Starting session setup...")
        try:
            jwt = setup_session()
        except SessionSetupError as exc:
            logger.error("Cannot start backfill without a valid session: %s", exc)
            sys.exit(1)

    init_db()
    session_factory = get_session_factory()

    with MahareraApiClient(jwt, config.scraper) as api_client:
        doc_downloader = DocumentDownloader(api_client)
        fetcher = RelatedEntityFetcher(api_client, doc_downloader)

        processed = 0
        failed = 0
        last_id = args.start_id

        try:
            with session_factory() as list_session:
                query = select(Project.id, Project.project_id, Project.registration_number,
                                Project.promoter_profile_id).where(Project.id > args.start_id).order_by(Project.id)
                if args.limit:
                    query = query.limit(args.limit)
                rows = list_session.execute(query).all()

            logger.info("Backfill starting | projects_to_process=%d | start_id=%d", len(rows), args.start_id)

            for db_id, project_id, registration_number, promoter_profile_id in rows:
                with session_factory() as session:
                    try:
                        fetcher.fetch_and_upsert(
                            session, db_id, project_id, registration_number, promoter_profile_id
                        )
                        processed += 1
                        last_id = db_id
                    except MahareraApiError:
                        raise
                    except Exception as exc:
                        failed += 1
                        logger.warning(
                            "Backfill failed for project_id=%s registration=%s: %s",
                            project_id, registration_number, exc,
                        )

                if processed % 10 == 0:
                    logger.info(
                        "Backfill progress | processed=%d | failed=%d | last_id=%d",
                        processed, failed, last_id,
                    )

        except KeyboardInterrupt:
            logger.warning("Backfill interrupted by user.")
        except MahareraApiError as exc:
            logger.error("API error — likely JWT expiry: %s", exc)

    logger.info(
        "Backfill complete | processed=%d | failed=%d | last_id=%d | resume with: "
        "python scripts/run_backfill.py --start-id %d",
        processed, failed, last_id, last_id,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
