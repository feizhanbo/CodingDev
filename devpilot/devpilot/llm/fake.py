"""Fake LLM client for testing."""

from __future__ import annotations

from devpilot.llm.base import LLMClient, LLMMessage, LLMResponse


class FakeLLMClient(LLMClient):
    """A deterministic LLM client that returns pre-configured responses."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.call_count = 0

    async def chat(
        self, messages: list[LLMMessage], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Return the next pre-configured response."""
        if self._index >= len(self._responses):
            raise RuntimeError("No more fake responses")
        response = self._responses[self._index]
        self._index += 1
        self.call_count += 1
        return response
