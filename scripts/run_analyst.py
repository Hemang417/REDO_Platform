"""
Entry point for the AI Investment Analyst pipeline.

Prerequisites (Claude):
    $env:ANTHROPIC_API_KEY = "sk-ant-..."

Prerequisites (Groq — free tier, no approval needed):
    $env:GROQ_API_KEY = "gsk_..."

Usage:
    python scripts/run_analyst.py --provider groq
    python scripts/run_analyst.py --provider claude
    python scripts/run_analyst.py --scored output/scored/maharera_scored_*.json
    python scripts/run_analyst.py --provider groq --min-score 50 --top 20

Exit codes:
    0  Completed
    1  Fatal error (config missing, API key not set, etc.)
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

from src.ai.claude_client import ClaudeClient, ClaudeClientError
from src.ai.groq_client import GroqClient, GroqClientError
from src.ai.maharera_analyst import MahareraAnalyst
from src.ai.storage import MemoStorage
from src.config.loader import load_ai_config, load_config
from src.models.developer_profile import DeveloperProfile
from src.models.scored_project import ScoredProject
from src.utils.logger import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate AI investment memos for scored MAHARERA projects."
    )
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--ai-config", default="config/ai_config.yaml")
    parser.add_argument(
        "--provider", choices=["claude", "groq"], default="claude",
        help="AI provider: 'claude' (ANTHROPIC_API_KEY) or 'groq' (GROQ_API_KEY). Default: claude."
    )
    parser.add_argument("--scored", default=None, help="Scored JSON file(s).")
    parser.add_argument("--intelligence", default=None, help="Developer profiles JSON file.")
    parser.add_argument(
        "--min-score", type=float, default=None,
        help="Override ai_config.yaml min_score_for_memo."
    )
    parser.add_argument("--top", type=int, default=10)
    return parser.parse_args()


def _load_json_list(path: str, model_cls):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    items = []
    for record in data:
        try:
            items.append(model_cls(**record))
        except Exception as exc:
            logging.getLogger(__name__).warning("Skipping invalid record: %s", exc)
    return items


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)
        ai_cfg = load_ai_config(args.ai_config)
    except Exception as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    # Override min_score from CLI if provided
    if args.min_score is not None:
        from dataclasses import replace as dc_replace
        ai_cfg = dc_replace(ai_cfg, min_score_for_memo=args.min_score)

    setup_logging(config.logging)
    logger = logging.getLogger(__name__)

    # Load projects
    scored_files = (
        [args.scored] if args.scored
        else sorted(glob.glob("output/scored/maharera_scored_*.json"))
    )
    if not scored_files:
        logger.error("No scored files found.")
        return 1

    all_projects: list[ScoredProject] = []
    for path in scored_files:
        all_projects.extend(_load_json_list(path, ScoredProject))
    logger.info("Loaded %d scored projects", len(all_projects))

    # Load developer profiles (optional but recommended)
    intel_file = args.intelligence or next(
        iter(sorted(glob.glob("output/intelligence/developer_profiles_*.json"), reverse=True)),
        None,
    )
    developer_index: dict = {}
    if intel_file and Path(intel_file).exists():
        profiles: list[DeveloperProfile] = _load_json_list(intel_file, DeveloperProfile)
        developer_index = {p.promoter_profile_id: p for p in profiles if p.promoter_profile_id}
        logger.info("Loaded %d developer profiles", len(profiles))
    else:
        logger.warning("No developer profiles found — memos will lack track record context.")

    # Build client + analyst
    try:
        if args.provider == "groq":
            client = GroqClient(ai_cfg)
            logger.info("Using Groq provider | model=%s", ai_cfg.groq_model)
        else:
            client = ClaudeClient(ai_cfg)
            logger.info("Using Claude provider | model=%s", ai_cfg.model)
    except (ClaudeClientError, GroqClientError) as exc:
        logger.error("%s", exc)
        return 1

    analyst = MahareraAnalyst(ai_cfg, client)
    storage = MemoStorage(ai_cfg.output_dir)

    memos, skipped = analyst.analyse_batch(all_projects, developer_index)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if memos:
        paths = storage.save(memos, run_id)
        logger.info("Output files:")
        for fmt, path in paths.items():
            logger.info("  %s: %s", fmt.upper(), path)

    # Console summary table
    top_n = sorted(memos, key=lambda m: m.opportunity_score, reverse=True)[:args.top]
    if top_n:
        print(f"\n{'RANK':<5} {'ACTION':<16} {'SCORE':>6}  {'CONF':>5}  {'REGISTRATION':<18} {'DEVELOPER'}")
        print("-" * 80)
        for rank, m in enumerate(top_n, 1):
            print(
                f"{rank:<5} {m.recommended_action.value:<16} "
                f"{m.opportunity_score:>6.1f}  "
                f"{m.confidence_score:>5.2f}  "
                f"{m.registration_number:<18} "
                f"{m.developer_name[:25]}"
            )
        print("-" * 80 + "\n")

    logger.info("Analyst complete | memos=%d | skipped=%d", len(memos), len(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
