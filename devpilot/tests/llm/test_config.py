"""Tests for LLMConfig."""

from __future__ import annotations

import pytest

from devpilot.llm.config import LLMConfig


class TestLLMConfig:
    def test_default_values(self) -> None:
        config = LLMConfig(_env_file=None)
        assert config.model == "gpt-4o"
        assert config.api_key == ""
        assert config.max_tokens == 4096
        assert config.temperature == 0.0

    def test_environment_variable_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEVPILOT_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("DEVPILOT_API_KEY", "sk-test-key")
        monkeypatch.setenv("DEVPILOT_MAX_TOKENS", "8192")
        monkeypatch.setenv("DEVPILOT_TEMPERATURE", "0.7")

        config = LLMConfig(_env_file=None)
        assert config.model == "gpt-4o-mini"
        assert config.api_key == "sk-test-key"
        assert config.max_tokens == 8192
        assert config.temperature == 0.7

    def test_env_prefix_is_devpilot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEVPILOT_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-other")
        monkeypatch.delenv("DEVPILOT_API_KEY", raising=False)

        config = LLMConfig(_env_file=None)
        assert config.model == "gpt-4o-mini"
        assert config.api_key == ""

    def test_explicit_construction_overrides_defaults(self) -> None:
        config = LLMConfig(model="o3", api_key="sk-x", max_tokens=1024, temperature=0.5)
        assert config.model == "o3"
        assert config.api_key == "sk-x"
        assert config.max_tokens == 1024
        assert config.temperature == 0.5
