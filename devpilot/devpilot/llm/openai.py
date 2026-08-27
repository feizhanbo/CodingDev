"""OpenAI LLM client."""

from __future__ import annotations

import time
from typing import Any

import openai

from devpilot.domain.decision import AgentDecision
from devpilot.llm.base import LLMClient, LLMMessage, LLMResponse
from devpilot.llm.config import LLMConfig


class OpenAIClient(LLMClient):
    """LLM client backed by the OpenAI API."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client = openai.AsyncOpenAI(api_key=config.api_key)

    async def chat(
        self, messages: list[LLMMessage], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Send a chat request and return a parsed AgentDecision."""
        openai_messages: list[dict[str, Any]] = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

        schema = AgentDecision.model_json_schema()
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "agent_decision",
                "schema": schema,
                "strict": False,
            },
        }

        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": openai_messages,
            "response_format": response_format,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
        }
        if tools:
            kwargs["tools"] = tools

        start = time.monotonic()
        completion = await self._client.chat.completions.create(**kwargs)
        latency_ms = int((time.monotonic() - start) * 1000)

        raw_content = completion.choices[0].message.content or "{}"
        decision = AgentDecision.model_validate_json(raw_content)

        tokens_used: int | None = None
        if completion.usage is not None:
            tokens_used = completion.usage.total_tokens

        return LLMResponse(
            decision=decision,
            model=completion.model,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            raw_response=raw_content,
        )
