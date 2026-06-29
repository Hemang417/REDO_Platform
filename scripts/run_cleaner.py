"""
Entry point for the MAHARERA data cleaning pipeline.

Reads raw JSON files from output/raw/, cleans each record, and writes
typed CleanProject records to output/clean/.

Usage:
    python scripts/run_cleaner.py
    python scripts/run_cleaner.py --input output/raw/maharera_projects_20260629_180758.json
    python scripts/run_cleaner.py --config /path/to/alt.yaml

Exit codes:
    0  Cleaning completed (possibly with some failures)
    1  Fatal error (config missing, input file unreadable, etc.)
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cleaner.maharera_cleaner import MahareraCleaner
from src.cleaner.storage import CleanStorage
from src.config.loader import load_config
from src.models.raw_project import RawProject
from src.utils.logger import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean MAHARERA raw JSON into typed CleanProject records."
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to settings YAML (default: config/settings.yaml)",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Specific raw JSON file to clean. Defaults to all files in raw_input_dir.",
    )
    return parser.parse_args()


def load_raw_projects(path: str) -> list[RawProject]:
    """Load a raw JSON file and validate each record into RawProject."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    projects = []
    for record in data:
        try:
            # scraped_at may be an ISO string — Pydantic handles coercion
            projects.append(RawProject(**record))
        except Exception as exc:
            logging.getLogger(__name__).warning("Skipping invalid raw record: %s", exc)
    return projects


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)
    except (FileNotFoundError, Exception) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    setup_logging(config.logging)
    logger = logging.getLogger(__name__)

    cleaner = MahareraCleaner(config.cleaner)
    storage = CleanStorage(config.cleaner)

    # Determine input files
    if args.input:
        input_files = [args.input]
    else:
        pattern = str(Path(config.cleaner.raw_input_dir) / "maharera_projects_*.json")
        input_files = sorted(glob.glob(pattern))

    if not input_files:
        logger.error("No raw input files found in %s", config.cleaner.raw_input_dir)
        return 1

    logger.info("Cleaning %d input file(s)", len(input_files))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    total_cleaned = 0
    total_failed = 0

    for input_path in input_files:
        logger.info("Processing: %s", input_path)
        try:
            raws = load_raw_projects(input_path)
        except Exception as exc:
            logger.error("Failed to load %s: %s", input_path, exc)
            continue

        cleaned, failed = cleaner.clean_batch(raws)
        total_cleaned += len(cleaned)
        total_failed += len(failed)

        if cleaned:
            paths = storage.save(cleaned, run_id, append=(total_cleaned > len(cleaned)))
            logger.info("Output files:")
            for fmt, path in paths.items():
                logger.info("  %s: %s", fmt.upper(), path)

        if failed:
            storage.save_failed(failed, run_id)

    logger.info(
        "Cleaning complete | cleaned=%d | failed=%d | total=%d",
        total_cleaned,
        total_failed,
        total_cleaned + total_failed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
