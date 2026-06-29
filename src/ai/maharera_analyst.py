"""
Orchestrates memo generation: select eligible projects → build brief →
call Claude → validate → cache result.

Single responsibility: pipeline coordination.
Prompt logic lives in prompt_builder.py; API calls in claude_client.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.ai.claude_client import ClaudeClient, ClaudeClientError
from src.ai.prompt_builder import build_project_brief
from src.config.loader import AiConfig
from src.models.developer_profile import DeveloperProfile
from src.models.investment_memo import InvestmentMemo, RecommendedAction
from src.models.scored_project import ScoredProject

logger = logging.getLogger(__name__)


class MahareraAnalyst:
    """Generates InvestmentMemo records for scored projects using Claude."""

    def __init__(
        self,
        config: AiConfig,
        client: ClaudeClient,
    ) -> None:
        self._cfg = config
        self._client = client
        Path(config.cache_dir).mkdir(parents=True, exist_ok=True)

    def analyse_batch(
        self,
        projects: list[ScoredProject],
        developer_index: dict[Optional[int], DeveloperProfile],
    ) -> tuple[list[InvestmentMemo], list[ScoredProject]]:
        """Generate memos for all eligible projects.

        Args:
            projects:         Scored projects to analyse.
            developer_index:  Maps promoter_profile_id → DeveloperProfile.
                              Use None key for name-only matched profiles.

        Returns:
            (memos, skipped) — skipped contains projects that were filtered out
            or failed.
        """
        eligible = [
            p for p in projects
            if p.opportunity_score >= self._cfg.min_score_for_memo
        ][:self._cfg.max_memos_per_run]

        logger.info(
            "Analysing %d eligible projects (of %d total, threshold=%.1f)",
            len(eligible),
            len(projects),
            self._cfg.min_score_for_memo,
        )

        memos: list[InvestmentMemo] = []
        skipped: list[ScoredProject] = [p for p in projects if p not in eligible]

        for project in eligible:
            memo = self._analyse_one(project, developer_index)
            if memo:
                memos.append(memo)
            else:
                skipped.append(project)

        logger.info(
            "Analysis complete | memos=%d | skipped=%d",
            len(memos),
            len(skipped),
        )
        return memos, skipped

    def _analyse_one(
        self,
        project: ScoredProject,
        developer_index: dict,
    ) -> Optional[InvestmentMemo]:
        """Generate (or load from cache) one InvestmentMemo."""
        cache_key = self._cache_key(project)
        cached = self._load_cache(cache_key)
        if cached:
            logger.debug("Cache hit for project_id=%s", project.project_id)
            return cached

        developer = developer_index.get(project.promoter_profile_id)
        brief = build_project_brief(project, developer)

        try:
            response = self._client.generate_memo(brief)
        except ClaudeClientError as exc:
            logger.error(
                "Claude API failed for project_id=%s: %s",
                project.project_id,
                exc,
            )
            return None

        result = response["result"]

        try:
            memo = InvestmentMemo(
                project_id=project.project_id,
                registration_number=project.registration_number,
                project_name=project.project_name,
                developer_name=project.developer_name,
                recommended_action=RecommendedAction(result["recommended_action"]),
                opportunity_thesis=result["opportunity_thesis"],
                risk_flags=result.get("risk_flags", []),
                data_gaps=result.get("data_gaps", []),
                confidence_score=float(result.get("confidence_score", 0.5)),
                opportunity_score=project.opportunity_score,
                track_record_score=developer.track_record_score if developer else None,
                construction_progress_pct=project.construction_progress_pct,
                delay_days=project.delay_days,
                extension_count=project.extension_count,
                model_used=response["model"],
                input_tokens=response["input_tokens"],
                output_tokens=response["output_tokens"],
            )
        except Exception as exc:
            logger.error(
                "Failed to construct InvestmentMemo for project_id=%s: %s",
                project.project_id,
                exc,
            )
            return None

        self._save_cache(cache_key, memo)
        return memo

    # ------------------------------------------------------------------
    # File-based cache: skip already-processed projects
    # ------------------------------------------------------------------

    def _cache_key(self, project: ScoredProject) -> str:
        """Hash the project's key metrics to form a stable cache key."""
        payload = f"{project.project_id}:{project.opportunity_score}:{self._cfg.model}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def _cache_path(self, key: str) -> str:
        return os.path.join(self._cfg.cache_dir, f"{key}.json")

    def _load_cache(self, key: str) -> Optional[InvestmentMemo]:
        path = self._cache_path(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                return InvestmentMemo(**json.load(fh))
        except Exception:
            return None

    def _save_cache(self, key: str, memo: InvestmentMemo) -> None:
        path = self._cache_path(key)
        tmp = path + ".tmp"
        data = memo.model_dump()
        data["generated_at"] = data["generated_at"].isoformat()
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)
