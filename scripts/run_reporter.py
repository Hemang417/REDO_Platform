"""
Entry point for the Deal Origination Report generator.

Reads outputs from all prior pipeline stages and produces a single
HTML report suitable for printing to PDF, plus a JSON summary.

Usage:
    python scripts/run_reporter.py
    python scripts/run_reporter.py --memos output/memos/investment_memos_*.json
    python scripts/run_reporter.py --memos path/to/memos.json --scored path/to/scored.json

Exit codes:
    0  Report written
    1  Fatal error (no input files found, config error, etc.)
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

from src.config.loader import load_config, load_scoring_config
from src.models.developer_profile import DeveloperProfile
from src.models.investment_memo import InvestmentMemo
from src.models.scored_project import ScoredProject
from src.reporting.html_renderer import render_html
from src.reporting.report_builder import build_report
from src.reporting.storage import ReportStorage
from src.utils.logger import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Deal Origination Report from REDO Platform pipeline outputs."
    )
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--rules", default="config/scoring_rules.yaml")
    parser.add_argument(
        "--memos", default=None,
        help="Investment memos JSON file. Defaults to latest in output/memos/."
    )
    parser.add_argument(
        "--scored", default=None,
        help="Scored projects JSON file. Defaults to latest in output/scored/."
    )
    parser.add_argument(
        "--intelligence", default=None,
        help="Developer profiles JSON file. Defaults to latest in output/intelligence/."
    )
    parser.add_argument(
        "--output-dir", default="output/reports",
        help="Directory to write report files. Default: output/reports/."
    )
    return parser.parse_args()


def _latest(pattern: str) -> str | None:
    matches = sorted(glob.glob(pattern), reverse=True)
    return matches[0] if matches else None


def _load_json_list(path: str, model_cls):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    items = []
    log = logging.getLogger(__name__)
    for record in data:
        try:
            items.append(model_cls(**record))
        except Exception as exc:
            log.warning("Skipping invalid %s record: %s", model_cls.__name__, exc)
    return items


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)
        scoring_cfg = load_scoring_config(args.rules)
    except Exception as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    setup_logging(config.logging)
    logger = logging.getLogger(__name__)

    # --- Resolve input files ---------------------------------------------------
    memos_path = args.memos or _latest("output/memos/investment_memos_*.json")
    scored_path = args.scored or _latest("output/scored/maharera_scored_*.json")
    intel_path = args.intelligence or _latest("output/intelligence/developer_profiles_*.json")

    if not memos_path or not Path(memos_path).exists():
        logger.error(
            "No investment memos found. Run run_analyst.py first. "
            "Expected: output/memos/investment_memos_*.json"
        )
        return 1
    if not scored_path or not Path(scored_path).exists():
        logger.error(
            "No scored projects found. Run run_scorer.py first. "
            "Expected: output/scored/maharera_scored_*.json"
        )
        return 1

    # --- Load data ------------------------------------------------------------
    memos: list[InvestmentMemo] = _load_json_list(memos_path, InvestmentMemo)
    logger.info("Loaded %d memos from %s", len(memos), Path(memos_path).name)

    projects: list[ScoredProject] = _load_json_list(scored_path, ScoredProject)
    logger.info("Loaded %d scored projects from %s", len(projects), Path(scored_path).name)

    developer_profiles: list[DeveloperProfile] = []
    if intel_path and Path(intel_path).exists():
        developer_profiles = _load_json_list(intel_path, DeveloperProfile)
        logger.info("Loaded %d developer profiles from %s", len(developer_profiles), Path(intel_path).name)
    else:
        logger.warning("No developer profiles found — report will omit developer league table.")

    if not memos:
        logger.error("Memos file loaded but contained no valid records.")
        return 1

    # --- Scoring weights for methodology section ------------------------------
    weights = {
        "construction_progress": scoring_cfg.weights.construction_progress,
        "delay_severity": scoring_cfg.weights.delay_severity,
        "extension_history": scoring_cfg.weights.extension_history,
        "project_viability": scoring_cfg.weights.project_viability,
        "location": scoring_cfg.weights.location,
    }

    # --- Build + render -------------------------------------------------------
    logger.info("Building report data...")
    report_data = build_report(
        memos=memos,
        projects=projects,
        developer_profiles=developer_profiles,
        scoring_weights=weights,
        scoring_rules_path=args.rules,
    )

    logger.info("Rendering HTML...")
    html_content = render_html(report_data)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    storage = ReportStorage(args.output_dir)
    paths = storage.save(report_data, html_content, run_id)

    # --- Console summary ------------------------------------------------------
    s = report_data.summary
    print(f"\n{'=' * 60}")
    print(f"  REDO Platform — Deal Origination Report")
    print(f"{'=' * 60}")
    print(f"  Projects scored  : {s.total_projects_scored}")
    print(f"  Memos generated  : {s.total_memos_generated}")
    print(f"  Flag for Review  : {s.flag_for_review_count}")
    print(f"  Monitor          : {s.monitor_count}")
    print(f"  Pass             : {s.pass_count}")
    print(f"  Top score        : {s.max_opportunity_score:.1f} / 100")
    print(f"  Top district     : {s.top_district}")
    print(f"{'=' * 60}")
    print(f"  HTML report : {paths.get('html', 'N/A')}")
    print(f"  JSON summary: {paths.get('json', 'N/A')}")
    print(f"{'=' * 60}\n")

    logger.info("Report complete | run_id=%s", run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
