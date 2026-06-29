"""
Main entry point for the MAHARERA data collection pipeline.

Prerequisites:
    Run scripts/setup_session.py first to obtain a valid JWT.

Usage:
    python scripts/run_collector.py
    python scripts/run_collector.py --end-page 2            # test run (2 pages, ~20 projects)
    python scripts/run_collector.py --start-page 50         # resume from page 50
    python scripts/run_collector.py --dry-run               # parse but do not write files
    python scripts/run_collector.py --config /path/to/alt.yaml

Exit codes:
    0  Collection completed (possibly with some failed detail fetches)
    1  Fatal error (JWT expired, config missing, etc.)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.loader import load_config, ScraperConfig
from src.scraper.browser_client import load_token, setup_session, SessionSetupError
from src.scraper.http_client import HttpClient
from src.scraper.maharera_api_client import MahareraApiClient
from src.scraper.maharera_collector import MahareraCollector
from src.scraper.maharera_parser import MahareraParser
from src.scraper.storage import RawStorage
from src.utils.logger import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect MAHARERA project data into raw JSON and CSV files."
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to settings YAML file (default: config/settings.yaml)",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=None,
        help="Override config start_page (1-indexed)",
    )
    parser.add_argument(
        "--end-page",
        type=int,
        default=None,
        help="Stop after this page (1-indexed). Use 2 for a quick test run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but do not write output files.",
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

    # Override config with CLI args
    scraper_cfg = config.scraper
    if args.start_page is not None or args.end_page is not None:
        from dataclasses import replace
        scraper_cfg = replace(
            scraper_cfg,
            start_page=args.start_page or scraper_cfg.start_page,
            end_page=args.end_page if args.end_page is not None else scraper_cfg.end_page,
        )

    # Obtain JWT
    jwt = None
    if not args.setup:
        jwt = load_token()

    if not jwt:
        logger.info("No valid token found. Starting session setup...")
        try:
            jwt = setup_session()
        except SessionSetupError as exc:
            logger.error("Cannot start collection without a valid session: %s", exc)
            sys.exit(1)

    # Dry run: disable storage writes
    storage_cfg = config.storage
    if args.dry_run:
        logger.info("DRY RUN mode: output files will NOT be written.")
        from dataclasses import replace as dc_replace
        storage_cfg = dc_replace(storage_cfg, json_enabled=False, csv_enabled=False)

    # Wire dependencies and run
    logger.info(
        "Starting collection | start_page=%d | end_page=%s",
        scraper_cfg.start_page,
        scraper_cfg.end_page or "all",
    )

    with HttpClient(scraper_cfg) as http_client:
        with MahareraApiClient(jwt, scraper_cfg) as api_client:
            collector = MahareraCollector(
                http_client=http_client,
                api_client=api_client,
                parser=MahareraParser(),
                storage=RawStorage(storage_cfg),
                scraper_config=scraper_cfg,
            )
            result = collector.collect()

    logger.info("Run complete: %s", result)

    if result.output_paths:
        logger.info("Output files:")
        for fmt, path in result.output_paths.items():
            if path:
                logger.info("  %s: %s", fmt.upper(), path)

    sys.exit(0)


if __name__ == "__main__":
    main()
