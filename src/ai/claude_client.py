"""
Thin wrapper around the Anthropic Python SDK.

Handles:
- API key loading from environment (ANTHROPIC_API_KEY)
- Retries with exponential backoff on rate-limit and server errors
- Structured output via tool_use (forces schema-conformant JSON)

Single responsibility: HTTP to the Claude API.
No prompt logic, no domain knowledge.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import anthropic

from src.config.loader import AiConfig

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 529}

# Tool definition for structured memo output
_MEMO_TOOL: dict = {
    "name": "write_investment_memo",
    "description": (
        "Write a structured investment memo for the MAHARERA project described in "
        "the project brief. Populate every field based solely on the provided data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "recommended_action": {
                "type": "string",
                "enum": ["FLAG_FOR_REVIEW", "MONITOR", "PASS"],
                "description": "Investment recommendation based on the project data.",
            },
            "opportunity_thesis": {
                "type": "string",
                "description": (
                    "2–3 sentence investment thesis citing specific metrics from "
                    "the brief. No invented facts."
                ),
            },
            "risk_flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of specific risk factors, each grounded in a data point "
                    "from the brief."
                ),
            },
            "data_gaps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Fields listed as null or missing in the brief.",
            },
            "confidence_score": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "How confident you are in this assessment given data completeness. "
                    "1.0 = all key fields present; lower for many null fields."
                ),
            },
        },
        "required": [
            "recommended_action",
            "opportunity_thesis",
            "risk_flags",
            "data_gaps",
            "confidence_score",
        ],
    },
}


class ClaudeClientError(Exception):
    """Raised when the API call fails after all retries."""


class ClaudeClient:
    """Makes structured Claude API calls for investment memo generation."""

    def __init__(self, config: AiConfig) -> None:
        self._cfg = config
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ClaudeClientError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Export it before running the analyst: "
                "set ANTHROPIC_API_KEY=sk-ant-..."
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate_memo(
        self,
        brief: str,
    ) -> dict[str, Any]:
        """Call Claude with the project brief and return the structured tool call input.

        Returns:
            Dict matching the write_investment_memo tool input schema.

        Raises:
            ClaudeClientError: After all retries are exhausted.
        """
        messages = [{"role": "user", "content": brief}]

        last_exc: Optional[Exception] = None
        for attempt in range(self._cfg.max_retries + 1):
            try:
                response = self._client.messages.create(  # type: ignore[call-overload]
                    model=self._cfg.model,
                    max_tokens=self._cfg.max_tokens,
                    system=self._cfg.system_prompt,
                    tools=[_MEMO_TOOL],
                    tool_choice={"type": "tool", "name": "write_investment_memo"},
                    messages=messages,
                )

                # Extract the tool call input
                for block in response.content:
                    if block.type == "tool_use" and block.name == "write_investment_memo":
                        return {
                            "result": block.input,
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                            "model": response.model,
                        }

                raise ClaudeClientError("Response contained no tool call block.")

            except anthropic.RateLimitError as exc:
                last_exc = exc
                wait = self._cfg.retry_backoff_factor ** attempt
                logger.warning("Rate limited — waiting %.1fs (attempt %d)", wait, attempt + 1)
                time.sleep(wait)

            except anthropic.APIStatusError as exc:
                if exc.status_code in _RETRYABLE_STATUS:
                    last_exc = exc
                    wait = self._cfg.retry_backoff_factor ** attempt
                    logger.warning(
                        "API error %d — waiting %.1fs (attempt %d)",
                        exc.status_code, wait, attempt + 1,
                    )
                    time.sleep(wait)
                else:
                    raise ClaudeClientError(f"Non-retryable API error: {exc}") from exc

            except anthropic.APIConnectionError as exc:
                last_exc = exc
                wait = self._cfg.retry_backoff_factor ** attempt
                logger.warning("Connection error — waiting %.1fs (attempt %d)", wait, attempt + 1)
                time.sleep(wait)

        raise ClaudeClientError(
            f"Claude API failed after {self._cfg.max_retries + 1} attempts: {last_exc}"
        )
