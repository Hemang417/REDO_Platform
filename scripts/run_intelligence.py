"""
Entry point for the Developer Intelligence pipeline.

Reads scored JSON files from output/scored/, aggregates by developer, and writes
DeveloperProfile records to output/intelligence/.

Usage:
    python scripts/run_intelligence.py
    python scripts/run_intelligence.py --input output/scored/maharera_scored_*.json
    python scripts/run_intelligence.py --top 20

Exit codes:
    0  Completed
    1  Fatal error
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

from src.config.loader import load_config, load_developer_scoring_config
from src.intelligence.developer_aggregator import DeveloperAggregator
from src.intelligence.storage import IntelligenceStorage
from src.models.scored_project import ScoredProject
from src.utils.logger import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build developer track-record profiles from scored MAHARERA projects."
    )
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--rules", default="config/scoring_rules.yaml")
    parser.add_argument(
        "--input", default=None,
        help="Specific scored JSON file(s). Defaults to all files in output/scored/.",
    )
    parser.add_argument(
        "--top", type=int, default=10,
        help="Print top-N developers by track_record_score (default: 10).",
    )
    return parser.parse_args()


def load_scored_projects(path: str) -> list[ScoredProject]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    projects = []
    for record in data:
        try:
            projects.append(ScoredProject(**record))
        except Exception as exc:
            logging.getLogger(__name__).warning("Skipping invalid record: %s", exc)
    return projects


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        dev_config = load_developer_scoring_config(args.rules)
    except Exception as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    setup_logging(config.logging)
    logger = logging.getLogger(__name__)

    aggregator = DeveloperAggregator(dev_config)
    storage = IntelligenceStorage("output/intelligence")

    if args.input:
        input_files = [args.input]
    else:
        input_files = sorted(glob.glob("output/scored/maharera_scored_*.json"))

    if not input_files:
        logger.error("No scored input files found.")
        return 1

    logger.info("Loading from %d file(s)", len(input_files))
    all_projects: list[ScoredProject] = []
    for path in input_files:
        all_projects.extend(load_scored_projects(path))

    logger.info("Loaded %d scored projects", len(all_projects))

    profiles = aggregator.aggregate(all_projects)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if profiles:
        paths = storage.save(profiles, run_id)
        logger.info("Output files:")
        for fmt, path in paths.items():
            logger.info("  %s: %s", fmt.upper(), path)

    # Console table
    top_n = profiles[:args.top]
    if top_n:
        print(f"\n{'RANK':<5} {'SCORE':>6}  {'DEVELOPER':<32} {'PROJS':>5}  {'COMP%':>6}  {'DISTRICT'}")
        print("-" * 75)
        for rank, p in enumerate(top_n, 1):
            comp_pct = f"{p.completion_rate*100:.0f}%" if p.completion_rate is not None else "N/A"
            print(
                f"{rank:<5} {p.track_record_score:>6.1f}  "
                f"{p.developer_name[:30]:<32} "
                f"{p.total_projects:>5}  "
                f"{comp_pct:>6}  "
                f"{p.primary_district or ''}"
            )
        print("-" * 75 + "\n")

    logger.info("Intelligence complete | %d developer profiles", len(profiles))
    return 0


if __name__ == "__main__":
    sys.exit(main())
