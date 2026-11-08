"""OpenAI-compatible LLM client."""

from __future__ import annotations

import time
import uuid
from typing import Any

import openai

from devpilot.llm.base import (
    LLMClient,
    LLMMessage,
    LLMRequestRecord,
    LLMResponse,
)
from devpilot.llm.config import LLMConfig
from devpilot.llm.decision_parser import parse_decision
from devpilot.llm.protocol import SCHEMA_HINT, prepare_messages


class OpenAIClient(LLMClient):
    """LLM client backed by the OpenAI-compatible API.

    Uses ``json_object`` response format for maximum compatibility
    (OpenAI, DeepSeek, Azure, local LLMs).  The AgentDecision schema
    is injected into the system prompt so the model knows the expected
    JSON structure.
    """

    # Schema description appended to the first system message
    _SCHEMA_HINT = SCHEMA_HINT

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        kwargs: dict[str, Any] = {"api_key": config.api_key, "max_retries": 0}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = openai.AsyncOpenAI(**kwargs)

    async def chat(
        self, messages: list[LLMMessage], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Send a chat request and return a parsed AgentDecision."""
        kwargs = {
            "model": self._config.model,
            "messages": prepare_messages(messages, tools, self._config),
            "response_format": {"type": "json_object"},
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
        }

        start = time.monotonic()
        record = LLMRequestRecord(request_id=uuid.uuid4().hex, model=self._config.model)
        self.last_request = record
        try:
            # Runtime owns retries so every transport attempt is observable.
            completion = await self._client.chat.completions.create(**kwargs)
            record.model = completion.model
            if completion.usage is not None:
                record.input_tokens = completion.usage.prompt_tokens
                record.output_tokens = completion.usage.completion_tokens
                record.total_tokens = completion.usage.total_tokens
            record.status = "parse_error"
            raw_content = completion.choices[0].message.content or "{}"
            decision = self._parse_decision(raw_content)
            record.status = "success"
            return LLMResponse(
                decision=decision,
                model=completion.model,
                tokens_used=record.total_tokens,
                latency_ms=int((time.monotonic() - start) * 1000),
                raw_response=raw_content,
            )
        except Exception as exc:
            record.error_type = type(exc).__name__
            raise
        finally:
            record.latency_ms = int((time.monotonic() - start) * 1000)

    _parse_decision = staticmethod(parse_decision)
