"""Tests for Module 5: prompt_builder, MahareraAnalyst (mocked Claude/Groq clients)."""

import json
import os
import tempfile
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.ai.maharera_analyst import MahareraAnalyst
from src.ai.prompt_builder import build_project_brief
from src.config.loader import AiConfig, load_ai_config
from src.models.developer_profile import DeveloperProfile
from src.models.investment_memo import InvestmentMemo, RecommendedAction
from src.models.scored_project import ScoredProject

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AI_CFG = AiConfig(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    request_timeout=60,
    max_retries=2,
    retry_backoff_factor=1.0,
    min_score_for_memo=0.0,
    max_memos_per_run=100,
    cache_dir="",          # overridden per test
    output_dir="output/memos",
    system_prompt="You are an analyst.",
)


def _make_scored(
    project_id: int = 42,
    opportunity_score: float = 55.0,
    district: str = "Pune",
    current_status: str = "Active",
    is_lapsed: bool = False,
) -> ScoredProject:
    return ScoredProject(
        project_id=project_id,
        registration_number=f"P{project_id:012d}",
        project_name="TEST TOWERS",
        developer_name="TEST DEVELOPER",
        district=district,
        current_status=current_status,
        is_lapsed=is_lapsed,
        is_deregistered=False,
        is_abeyance=False,
        delay_days=400,
        is_delayed=True,
        construction_progress_pct=65.0,
        extension_count=1,
        proposed_completion_date=date(2022, 12, 31),
        opportunity_score=opportunity_score,
        factor_scores={
            "construction_progress": 1.0, "delay_severity": 1.0,
            "extension_history": 0.8, "project_viability": 1.0, "location": 1.0,
        },
        location_tier="tier1",
        detail_url="https://example.com",
        source_url="https://example.com",
        scraped_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        cleaned_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        scored_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        promoter_profile_id=101,
    )


def _make_developer() -> DeveloperProfile:
    return DeveloperProfile(
        promoter_profile_id=101,
        developer_name="TEST DEVELOPER",
        total_projects=5,
        active_projects=3,
        completed_projects=2,
        lapsed_projects=0,
        deregistered_projects=0,
        abeyance_projects=0,
        completion_rate=0.40,
        on_time_rate=0.60,
        lapse_rate=0.0,
        avg_delay_days=350.0,
        max_delay_days=800,
        avg_extensions=1.2,
        track_record_score=62.5,
        districts=["Pune", "Thane"],
        primary_district="Pune",
        project_ids=[1, 2, 3, 4, 42],
        computed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )


def _mock_client_response() -> dict:
    return {
        "result": {
            "recommended_action": "FLAG_FOR_REVIEW",
            "opportunity_thesis": (
                "TEST TOWERS is 65.0% complete with a 400-day delay, indicating a "
                "classic last-mile funding gap. The developer has a 40% completion "
                "rate across 5 projects, suggesting moderate track record."
            ),
            "risk_flags": [
                "Project is 400 days overdue against its proposed completion date.",
                "Developer on-time rate is 60% across 5 projects.",
            ],
            "data_gaps": [],
            "confidence_score": 0.85,
        },
        "input_tokens": 420,
        "output_tokens": 180,
        "model": "claude-sonnet-4-6",
    }


# ---------------------------------------------------------------------------
# build_project_brief
# ---------------------------------------------------------------------------

class TestBuildProjectBrief:
    def test_contains_registration_number(self):
        brief = build_project_brief(_make_scored(), _make_developer())
        assert "P000000000042" in brief

    def test_contains_project_name(self):
        brief = build_project_brief(_make_scored(), _make_developer())
        assert "TEST TOWERS" in brief

    def test_contains_opportunity_score(self):
        brief = build_project_brief(_make_scored(), _make_developer())
        assert "55.0" in brief

    def test_contains_delay_days(self):
        brief = build_project_brief(_make_scored(), _make_developer())
        assert "400" in brief

    def test_contains_developer_stats(self):
        brief = build_project_brief(_make_scored(), _make_developer())
        assert "40%" in brief   # completion rate

    def test_none_developer_handled(self):
        brief = build_project_brief(_make_scored(), developer=None)
        assert "No developer profile available" in brief

    def test_null_field_shown_as_data_gap(self):
        project = _make_scored()
        # construction_progress_pct is not None for this project
        # Make a project with a None field
        project_with_null = project.model_copy(update={"construction_progress_pct": None})
        brief = build_project_brief(project_with_null, None)
        assert "null (data gap)" in brief

    def test_location_tier_included(self):
        brief = build_project_brief(_make_scored(district="Pune"), None)
        assert "TIER1" in brief.upper()

    def test_factor_scores_listed(self):
        brief = build_project_brief(_make_scored(), None)
        assert "Construction Progress" in brief
        assert "Delay Severity" in brief


# ---------------------------------------------------------------------------
# MahareraAnalyst (mocked client)
# ---------------------------------------------------------------------------

class TestMahareraAnalyst:
    def _make_analyst(self, tmp_dir: str) -> MahareraAnalyst:
        from dataclasses import replace
        cfg = replace(_AI_CFG, cache_dir=tmp_dir)
        mock_client = MagicMock()
        mock_client.generate_memo.return_value = _mock_client_response()
        return MahareraAnalyst(cfg, mock_client)

    def test_returns_investment_memo(self):
        with tempfile.TemporaryDirectory() as tmp:
            analyst = self._make_analyst(tmp)
            memos, skipped = analyst.analyse_batch(
                [_make_scored()], {101: _make_developer()}
            )
        assert len(memos) == 1
        assert isinstance(memos[0], InvestmentMemo)

    def test_memo_recommended_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            analyst = self._make_analyst(tmp)
            memos, _ = analyst.analyse_batch([_make_scored()], {101: _make_developer()})
        assert memos[0].recommended_action == RecommendedAction.FLAG_FOR_REVIEW

    def test_memo_contains_key_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            analyst = self._make_analyst(tmp)
            memos, _ = analyst.analyse_batch([_make_scored()], {101: _make_developer()})
        memo = memos[0]
        assert memo.opportunity_score == 55.0
        assert memo.construction_progress_pct == 65.0
        assert memo.delay_days == 400

    def test_memo_confidence_score_in_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            analyst = self._make_analyst(tmp)
            memos, _ = analyst.analyse_batch([_make_scored()], {101: _make_developer()})
        assert 0.0 <= memos[0].confidence_score <= 1.0

    def test_below_threshold_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            from dataclasses import replace
            cfg = replace(_AI_CFG, cache_dir=tmp, min_score_for_memo=80.0)
            mock_client = MagicMock()
            analyst = MahareraAnalyst(cfg, mock_client)
            memos, skipped = analyst.analyse_batch(
                [_make_scored(opportunity_score=55.0)], {}
            )
        assert len(memos) == 0
        assert len(skipped) == 1
        mock_client.generate_memo.assert_not_called()

    def test_cache_prevents_duplicate_api_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            analyst = self._make_analyst(tmp)
            project = _make_scored()
            # First call
            analyst.analyse_batch([project], {101: _make_developer()})
            # Second call — should hit cache
            analyst.analyse_batch([project], {101: _make_developer()})
        # API should have been called exactly once
        assert analyst._client.generate_memo.call_count == 1

    def test_api_failure_returns_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            from dataclasses import replace
            from src.ai.claude_client import ClaudeClientError
            cfg = replace(_AI_CFG, cache_dir=tmp)
            mock_client = MagicMock()
            mock_client.generate_memo.side_effect = ClaudeClientError("API down")
            analyst = MahareraAnalyst(cfg, mock_client)
            memos, skipped = analyst.analyse_batch([_make_scored()], {})
        assert len(memos) == 0
        assert len(skipped) == 1

    def test_max_memos_per_run_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            from dataclasses import replace
            cfg = replace(_AI_CFG, cache_dir=tmp, max_memos_per_run=3)
            mock_client = MagicMock()
            mock_client.generate_memo.return_value = _mock_client_response()
            analyst = MahareraAnalyst(cfg, mock_client)
            projects = [_make_scored(project_id=i) for i in range(1, 11)]
            memos, skipped = analyst.analyse_batch(projects, {})
        assert len(memos) == 3
        assert len(skipped) == 7

    def test_developer_track_record_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            analyst = self._make_analyst(tmp)
            memos, _ = analyst.analyse_batch([_make_scored()], {101: _make_developer()})
        assert memos[0].track_record_score == 62.5

    def test_missing_developer_produces_none_track_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            analyst = self._make_analyst(tmp)
            memos, _ = analyst.analyse_batch([_make_scored()], {})
        assert memos[0].track_record_score is None


# ---------------------------------------------------------------------------
# load_ai_config integration
# ---------------------------------------------------------------------------

class TestLoadAiConfig:
    def test_loads_from_file(self):
        cfg = load_ai_config("config/ai_config.yaml")
        assert "claude" in cfg.model
        assert cfg.max_tokens > 0
        assert isinstance(cfg.system_prompt, str)
        assert len(cfg.system_prompt) > 50

    def test_system_prompt_contains_constraint(self):
        cfg = load_ai_config("config/ai_config.yaml")
        assert "CRITICAL" in cfg.system_prompt or "constraint" in cfg.system_prompt.lower()

    def test_groq_model_loaded(self):
        cfg = load_ai_config("config/ai_config.yaml")
        assert cfg.groq_model  # non-empty string
        assert cfg.groq_max_tokens > 0


# ---------------------------------------------------------------------------
# GroqClient (mocked SDK)
# ---------------------------------------------------------------------------

class TestGroqClient:
    """Tests GroqClient in isolation using mocked Groq SDK."""

    def _make_groq_response(self, model: str = "llama-3.3-70b-versatile") -> MagicMock:
        """Build a fake Groq API response matching the SDK structure."""
        tool_call = MagicMock()
        tool_call.function.arguments = json.dumps({
            "recommended_action": "MONITOR",
            "opportunity_thesis": "Test thesis citing 65% construction and 400-day delay.",
            "risk_flags": ["Project is 400 days overdue."],
            "data_gaps": [],
            "confidence_score": 0.75,
        })
        choice = MagicMock()
        choice.message.tool_calls = [tool_call]
        usage = MagicMock()
        usage.prompt_tokens = 300
        usage.completion_tokens = 150
        response = MagicMock()
        response.choices = [choice]
        response.usage = usage
        response.model = model
        return response

    @patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key"})
    @patch("src.ai.groq_client.Groq")
    def test_generate_memo_returns_correct_shape(self, mock_groq_cls):
        from src.ai.groq_client import GroqClient
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.return_value = self._make_groq_response()
        mock_groq_cls.return_value = mock_instance

        client = GroqClient(_AI_CFG)
        result = client.generate_memo("Test project brief")

        assert "result" in result
        assert "input_tokens" in result
        assert "output_tokens" in result
        assert "model" in result
        assert result["input_tokens"] == 300
        assert result["output_tokens"] == 150

    @patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key"})
    @patch("src.ai.groq_client.Groq")
    def test_generate_memo_result_fields(self, mock_groq_cls):
        from src.ai.groq_client import GroqClient
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.return_value = self._make_groq_response()
        mock_groq_cls.return_value = mock_instance

        client = GroqClient(_AI_CFG)
        result = client.generate_memo("Test project brief")

        assert result["result"]["recommended_action"] == "MONITOR"
        assert result["result"]["confidence_score"] == 0.75
        assert isinstance(result["result"]["risk_flags"], list)

    def test_missing_api_key_raises(self):
        from src.ai.groq_client import GroqClient, GroqClientError
        env = {k: v for k, v in os.environ.items() if k != "GROQ_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(GroqClientError, match="GROQ_API_KEY"):
                GroqClient(_AI_CFG)

    @patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key"})
    @patch("src.ai.groq_client.Groq")
    def test_rate_limit_retries(self, mock_groq_cls):
        from groq import RateLimitError
        from src.ai.groq_client import GroqClient, GroqClientError
        mock_instance = MagicMock()
        # Always raise RateLimitError
        mock_instance.chat.completions.create.side_effect = RateLimitError(
            message="rate limited", response=MagicMock(status_code=429), body={}
        )
        mock_groq_cls.return_value = mock_instance

        from dataclasses import replace
        cfg = replace(_AI_CFG, max_retries=2, retry_backoff_factor=0.01)
        client = GroqClient(cfg)
        with patch("src.ai.groq_client.time.sleep"):
            with pytest.raises(GroqClientError, match="Groq API failed after"):
                client.generate_memo("Test")

        # Should have tried max_retries + 1 = 3 times
        assert mock_instance.chat.completions.create.call_count == 3

    @patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key"})
    @patch("src.ai.groq_client.Groq")
    def test_analyst_works_with_groq_client(self, mock_groq_cls):
        """End-to-end: MahareraAnalyst accepts GroqClient as a drop-in."""
        from src.ai.groq_client import GroqClient
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.return_value = self._make_groq_response()
        mock_groq_cls.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmp:
            from dataclasses import replace
            cfg = replace(_AI_CFG, cache_dir=tmp)
            client = GroqClient(cfg)
            analyst = MahareraAnalyst(cfg, client)
            memos, skipped = analyst.analyse_batch([_make_scored()], {101: _make_developer()})

        assert len(memos) == 1
        assert memos[0].recommended_action == RecommendedAction.MONITOR
        assert memos[0].confidence_score == 0.75
