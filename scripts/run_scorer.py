"""
Entry point for the MAHARERA investment scoring pipeline.

Reads clean JSON files from output/clean/, scores each project, and writes
ranked ScoredProject records to output/scored/.

Usage:
    python scripts/run_scorer.py
    python scripts/run_scorer.py --input output/clean/maharera_clean_*.json
    python scripts/run_scorer.py --top 50   # print top-N to console
    python scripts/run_scorer.py --config config/settings.yaml --rules config/scoring_rules.yaml

Exit codes:
    0  Scoring completed
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

from src.cleaner.maharera_cleaner import MahareraCleaner
from src.config.loader import load_config, load_scoring_config
from src.models.clean_project import CleanProject
from src.scorer.maharera_scorer import MahareraScorer
from src.scorer.storage import ScoredStorage
from src.utils.logger import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score cleaned MAHARERA projects for AIF investment opportunities."
    )
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--rules", default="config/scoring_rules.yaml")
    parser.add_argument(
        "--input", default=None,
        help="Specific clean JSON file(s). Defaults to all files in clean_output_dir.",
    )
    parser.add_argument(
        "--top", type=int, default=10,
        help="Print top-N projects to console after scoring (default: 10).",
    )
    parser.add_argument(
        "--min-score", type=float, default=0.0,
        help="Only save projects with opportunity_score >= this value.",
    )
    return parser.parse_args()


def load_clean_projects(path: str) -> list[CleanProject]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    projects = []
    for record in data:
        try:
            projects.append(CleanProject(**record))
        except Exception as exc:
            logging.getLogger(__name__).warning("Skipping invalid record: %s", exc)
    return projects


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)
        scoring_config = load_scoring_config(args.rules)
    except (FileNotFoundError, Exception) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    setup_logging(config.logging)
    logger = logging.getLogger(__name__)

    scorer = MahareraScorer(scoring_config)
    storage = ScoredStorage("output/scored")

    if args.input:
        input_files = [args.input]
    else:
        pattern = str(Path(config.cleaner.clean_output_dir) / "maharera_clean_*.json")
        input_files = sorted(glob.glob(pattern))

    if not input_files:
        logger.error("No clean input files found.")
        return 1

    logger.info("Scoring %d input file(s)", len(input_files))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    all_scored = []

    for input_path in input_files:
        logger.info("Processing: %s", input_path)
        projects = load_clean_projects(input_path)
        scored = scorer.score_batch(projects)
        all_scored.extend(scored)

    # Filter by min score
    if args.min_score > 0:
        before = len(all_scored)
        all_scored = [p for p in all_scored if p.opportunity_score >= args.min_score]
        logger.info("Filtered to min_score=%.1f: %d → %d projects", args.min_score, before, len(all_scored))

    # Sort by score descending
    all_scored.sort(key=lambda p: p.opportunity_score, reverse=True)

    if all_scored:
        paths = storage.save(all_scored, run_id)
        logger.info("Output files:")
        for fmt, path in paths.items():
            logger.info("  %s: %s", fmt.upper(), path)

    # Print top-N to console
    top_n = all_scored[:args.top]
    if top_n:
        print(f"\n{'-'*80}")
        print(f"{'RANK':<5} {'SCORE':>6}  {'REGISTRATION':<18} {'DEVELOPER':<30} {'DISTRICT':<20}")
        print(f"{'-'*80}")
        for rank, p in enumerate(top_n, 1):
            print(
                f"{rank:<5} {p.opportunity_score:>6.1f}  "
                f"{p.registration_number:<18} "
                f"{p.developer_name[:28]:<30} "
                f"{p.district:<20}"
            )
        print(f"{'-'*80}\n")

    logger.info("Scoring complete | total=%d", len(all_scored))
    return 0


if __name__ == "__main__":
    sys.exit(main())
