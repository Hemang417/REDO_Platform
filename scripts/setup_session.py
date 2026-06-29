"""
Run this script ONCE before the first collection run, or whenever the JWT expires.

Opens a Chrome window. Solve the CAPTCHA within 90 seconds.
Saves the JWT to config/maharera_token.json.

Usage:
    python scripts/setup_session.py
"""

import sys
from pathlib import Path

# Allow imports from src/ without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from src.config.loader import load_config
from src.utils.logger import setup_logging
from src.scraper.browser_client import setup_session, SessionSetupError


def main() -> None:
    config = load_config("config/settings.yaml")
    setup_logging(config.logging)
    logger = logging.getLogger(__name__)

    logger.info("Starting MAHARERA session setup...")
    logger.info(
        "A Chrome browser will open. Navigate to a MAHARERA project page, "
        "solve the CAPTCHA, and press Submit."
    )

    try:
        token = setup_session()
        logger.info("Session setup complete. JWT saved to config/maharera_token.json.")
        logger.info("JWT preview: %s...", token[:40])
        logger.info("You can now run: python scripts/run_collector.py")
    except SessionSetupError as exc:
        logger.error("Session setup failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
