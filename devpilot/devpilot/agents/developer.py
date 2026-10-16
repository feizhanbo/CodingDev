"""Developer agent."""

from __future__ import annotations

import time
import uuid

from devpilot.domain.decision import AgentDecision
from devpilot.llm import tools_to_openai_format
from devpilot.llm.base import LLMClient, LLMMessage, LLMRequestRecord
from devpilot.tools.registry import ToolRegistry


class DeveloperAgent:
    """LLM-backed agent that produces decisions from context."""

    def __init__(self, llm_client: LLMClient, registry: ToolRegistry) -> None:
        self.llm_client = llm_client
        self.registry = registry
        self.last_request: LLMRequestRecord | None = None

    async def decide(self, context: list[LLMMessage]) -> AgentDecision:
        """Get agent decision from LLM."""
        tools = tools_to_openai_format(self.registry)
        start = time.monotonic()
        self.llm_client.last_request = None
        record = LLMRequestRecord(request_id=uuid.uuid4().hex)
        self.last_request = record
        try:
            response = await self.llm_client.chat(context, tools)
            record.model = response.model
            record.total_tokens = response.tokens_used
            record.status = "success"
            return response.decision
        except Exception as exc:
            record.error_type = type(exc).__name__
            raise
        finally:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            self.last_request = self.llm_client.last_request or record
