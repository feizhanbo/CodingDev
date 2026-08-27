"""Tests for FakeLLMClient."""

from __future__ import annotations

import pytest

from devpilot.domain.decision import AgentDecision, FinishIntent
from devpilot.llm.base import LLMMessage, LLMResponse
from devpilot.llm.fake import FakeLLMClient


def _make_response(model: str = "gpt-4o") -> LLMResponse:
    return LLMResponse(
        decision=AgentDecision(finish=FinishIntent(summary="done", risk="low")),
        model=model,
        tokens_used=100,
        latency_ms=50,
    )


class TestFakeLLMClient:
    async def test_returns_responses_in_order(self) -> None:
        responses = [
            _make_response("model-a"),
            _make_response("model-b"),
        ]
        client = FakeLLMClient(responses)
        messages = [LLMMessage(role="user", content="hello")]

        r1 = await client.chat(messages)
        assert r1.model == "model-a"

        r2 = await client.chat(messages)
        assert r2.model == "model-b"

    async def test_raises_runtime_error_when_exhausted(self) -> None:
        client = FakeLLMClient([_make_response()])
        messages = [LLMMessage(role="user", content="hello")]

        await client.chat(messages)
        with pytest.raises(RuntimeError, match="No more fake responses"):
            await client.chat(messages)

    async def test_call_count_increments(self) -> None:
        client = FakeLLMClient([_make_response(), _make_response()])
        messages = [LLMMessage(role="user", content="hello")]

        assert client.call_count == 0
        await client.chat(messages)
        assert client.call_count == 1
        await client.chat(messages)
        assert client.call_count == 2

    async def test_empty_responses_raises_immediately(self) -> None:
        client = FakeLLMClient([])
        messages = [LLMMessage(role="user", content="hello")]
        with pytest.raises(RuntimeError, match="No more fake responses"):
            await client.chat(messages)

    async def test_tools_argument_accepted(self) -> None:
        client = FakeLLMClient([_make_response()])
        messages = [LLMMessage(role="user", content="hello")]
        tools = [{"type": "function", "function": {"name": "read_file"}}]
        response = await client.chat(messages, tools=tools)
        assert response.model == "gpt-4o"
        assert client.call_count == 1
