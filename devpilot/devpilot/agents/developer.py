"""Developer agent."""

from __future__ import annotations

from devpilot.domain.decision import AgentDecision
from devpilot.llm import tools_to_openai_format
from devpilot.llm.base import LLMClient, LLMMessage
from devpilot.tools.registry import ToolRegistry


class DeveloperAgent:
    """LLM-backed agent that produces decisions from context."""

    def __init__(self, llm_client: LLMClient, registry: ToolRegistry) -> None:
        self.llm_client = llm_client
        self.registry = registry

    async def decide(self, context: list[LLMMessage]) -> AgentDecision:
        """Get agent decision from LLM."""
        tools = tools_to_openai_format(self.registry)
        response = await self.llm_client.chat(context, tools)
        return response.decision
