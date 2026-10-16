"""LLM client base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from devpilot.domain.decision import AgentDecision


class LLMMessage(BaseModel):
    """A single message in an LLM conversation."""

    role: Literal['system', 'user', 'assistant', 'tool']
    content: str


class LLMResponse(BaseModel):
    """A parsed response from the LLM."""

    decision: AgentDecision
    model: str
    tokens_used: int | None = None
    latency_ms: int | None = None
    raw_response: str | None = None


class LLMRequestRecord(BaseModel):
    """One transport attempt; unknown usage stays unknown."""

    request_id: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int = 0
    status: Literal["success", "api_error", "parse_error"] = "api_error"
    error_type: str | None = None


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    last_request: LLMRequestRecord | None = None

    @abstractmethod
    async def chat(
        self, messages: list[LLMMessage], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Send a chat request and return a parsed decision."""
        ...
