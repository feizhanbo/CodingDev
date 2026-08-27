"""Tests for DeveloperAgent."""

from __future__ import annotations

from devpilot.agents.developer import DeveloperAgent
from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
from devpilot.llm.base import LLMMessage, LLMResponse
from devpilot.llm.fake import FakeLLMClient


def _make_response(
    decision: AgentDecision | None = None,
) -> LLMResponse:
    return LLMResponse(
        decision=decision or AgentDecision(
            action=ToolAction(tool="repo.read_file", arguments={"path": "a"})
        ),
        model="fake-model",
        tokens_used=10,
    )


class TestDeveloperAgentDecide:
    async def test_decide_calls_llm_and_returns_decision(
        self, registry
    ) -> None:
        decision = AgentDecision(
            action=ToolAction(
                tool="repo.search_code", arguments={"query": "orders"}
            )
        )
        client = FakeLLMClient([_make_response(decision)])
        agent = DeveloperAgent(client, registry)
        messages = [LLMMessage(role="user", content="hello")]
        result = await agent.decide(messages)
        assert result is decision
        assert client.call_count == 1

    async def test_decide_returns_finish_decision(
        self, registry
    ) -> None:
        decision = AgentDecision(
            finish=FinishIntent(summary="done", risk="low")
        )
        client = FakeLLMClient([_make_response(decision)])
        agent = DeveloperAgent(client, registry)
        result = await agent.decide([LLMMessage(role="user", content="go")])
        assert result.finish is not None
        assert result.finish.summary == "done"

    async def test_decide_passes_tool_schemas_to_llm(
        self, registry
    ) -> None:
        decision = AgentDecision(
            action=ToolAction(
                tool="repo.list_files", arguments={"path": "."}
            )
        )

        class SpyClient(FakeLLMClient):
            received_tools: list[dict] | None = None

            async def chat(self, messages, tools=None):  # type: ignore[no-untyped-def]
                self.received_tools = tools
                return await super().chat(messages, tools)

        spy = SpyClient([_make_response(decision)])
        agent = DeveloperAgent(spy, registry)
        await agent.decide([LLMMessage(role="user", content="hi")])
        assert spy.received_tools is not None
        assert len(spy.received_tools) > 0
        tool_names = [
            t["function"]["name"] for t in spy.received_tools
        ]
        assert "repo.read_file" in tool_names
        assert "code.apply_patch" in tool_names
