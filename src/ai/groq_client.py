"""
Thin wrapper around the Groq Python SDK (OpenAI-compatible).

Drop-in alternative to ClaudeClient — same generate_memo() signature,
same return dict shape: {"result": {...}, "input_tokens": N, "output_tokens": N, "model": "..."}.

Uses function calling to force schema-conformant JSON (mirrors ClaudeClient's tool_use strategy).
API key loaded from GROQ_API_KEY environment variable.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

from groq import Groq, RateLimitError, APIStatusError, APIConnectionError, BadRequestError

from src.config.loader import AiConfig

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 529}

# Mirrors the Claude tool definition — same schema, different calling convention
_MEMO_FUNCTION: dict = {
    "name": "write_investment_memo",
    "description": (
        "Write a structured investment memo for the MAHARERA project described in "
        "the project brief. Populate every field based solely on the provided data."
    ),
    "parameters": {
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
                    "2-3 sentence investment thesis citing specific metrics from "
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


class GroqClientError(Exception):
    """Raised when the Groq API call fails after all retries."""


class GroqClient:
    """Makes structured Groq API calls for investment memo generation.

    Identical public interface to ClaudeClient — MahareraAnalyst accepts either.
    """

    def __init__(self, config: AiConfig) -> None:
        self._cfg = config
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise GroqClientError(
                "GROQ_API_KEY environment variable is not set. "
                "Set it before running: $env:GROQ_API_KEY = 'gsk_...'"
            )
        self._client = Groq(api_key=api_key)

    def generate_memo(self, brief: str) -> dict[str, Any]:
        """Call Groq with the project brief and return the structured function call result.

        Returns:
            {"result": {...}, "input_tokens": N, "output_tokens": N, "model": "..."}

        Raises:
            GroqClientError: After all retries are exhausted.
        """
        messages = [
            {"role": "system", "content": self._cfg.system_prompt},
            {"role": "user", "content": brief},
        ]

        last_exc: Optional[Exception] = None
        for attempt in range(self._cfg.max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._cfg.groq_model,
                    max_tokens=self._cfg.groq_max_tokens,
                    messages=messages,
                    tools=[{"type": "function", "function": _MEMO_FUNCTION}],
                    tool_choice={"type": "function", "function": {"name": "write_investment_memo"}},
                )

                choice = response.choices[0]
                tool_calls = choice.message.tool_calls
                if not tool_calls:
                    raise GroqClientError("Response contained no function call.")

                raw_args = tool_calls[0].function.arguments
                result = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                usage = response.usage
                return {
                    "result": result,
                    "input_tokens": usage.prompt_tokens if usage else 0,
                    "output_tokens": usage.completion_tokens if usage else 0,
                    "model": response.model,
                }

            except RateLimitError as exc:
                last_exc = exc
                wait = self._cfg.retry_backoff_factor ** attempt
                logger.warning("Groq rate limited — waiting %.1fs (attempt %d)", wait, attempt + 1)
                time.sleep(wait)

            except BadRequestError as exc:
                # Groq occasionally fails to serialise the function call JSON mid-stream.
                # The error body contains `failed_generation` with the partial output;
                # retrying usually succeeds.
                body = exc.body or {}
                if isinstance(body, dict) and body.get("error", {}).get("code") == "tool_use_failed":
                    last_exc = exc
                    wait = self._cfg.retry_backoff_factor ** attempt
                    logger.warning(
                        "Groq tool_use_failed (malformed JSON in function call) — "
                        "retrying in %.1fs (attempt %d)", wait, attempt + 1,
                    )
                    time.sleep(wait)
                else:
                    raise GroqClientError(f"Non-retryable Groq bad request: {exc}") from exc

            except APIStatusError as exc:
                if exc.status_code in _RETRYABLE_STATUS:
                    last_exc = exc
                    wait = self._cfg.retry_backoff_factor ** attempt
                    logger.warning(
                        "Groq API error %d — waiting %.1fs (attempt %d)",
                        exc.status_code, wait, attempt + 1,
                    )
                    time.sleep(wait)
                else:
                    raise GroqClientError(f"Non-retryable Groq API error: {exc}") from exc

            except APIConnectionError as exc:
                last_exc = exc
                wait = self._cfg.retry_backoff_factor ** attempt
                logger.warning("Groq connection error — waiting %.1fs (attempt %d)", wait, attempt + 1)
                time.sleep(wait)

        raise GroqClientError(
            f"Groq API failed after {self._cfg.max_retries + 1} attempts: {last_exc}"
        )
