"""Tests for LLM prompt templates and tool schema conversion."""

from __future__ import annotations

from devpilot.llm.prompts import (
    REPOSITORY_INSTRUCTIONS,
    SYSTEM_PROMPT,
    build_system_prompt,
)
from devpilot.llm.tool_schema import tools_to_openai_format
from devpilot.runtime import RuntimeConfig
from devpilot.tools import ToolRegistry
from devpilot.tools.code import CreateFile
from devpilot.tools.repo import ListFiles


class TestBuildSystemPrompt:
    def test_returns_non_empty_string(self) -> None:
        prompt = build_system_prompt(RuntimeConfig())
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_contains_role_description(self) -> None:
        prompt = build_system_prompt(RuntimeConfig())
        assert "DevPilot" in prompt
        assert "development task agent" in prompt

    def test_policy_contains_max_steps_and_test_retries(self) -> None:
        config = RuntimeConfig(max_steps=42, max_test_retries=7)
        prompt = build_system_prompt(config)
        assert "42" in prompt
        assert "7" in prompt

    def test_repository_instructions_mention_shopflow(self) -> None:
        prompt = build_system_prompt(RuntimeConfig())
        assert "ShopFlow" in prompt

    def test_prompt_layers_are_present(self) -> None:
        prompt = build_system_prompt(RuntimeConfig())
        # All three layers should appear in order.
        assert SYSTEM_PROMPT in prompt
        assert REPOSITORY_INSTRUCTIONS in prompt
        # The formatted policy (not the template with {max_steps}) is present.
        assert "{max_steps}" not in prompt
        assert "{max_test_retries}" not in prompt


class TestToolsToOpenAIFormat:
    def test_returns_correct_format(self) -> None:
        reg = ToolRegistry()
        reg.register(ListFiles())
        reg.register(CreateFile())
        tools = tools_to_openai_format(reg)
        assert isinstance(tools, list)
        assert len(tools) == 2
        for tool in tools:
            assert tool["type"] == "function"
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]
            assert isinstance(tool["function"]["parameters"], dict)

    def test_empty_registry(self) -> None:
        tools = tools_to_openai_format(ToolRegistry())
        assert tools == []
