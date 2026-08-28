"""LLM configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """Configuration for the LLM client, loaded from environment variables."""

    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.0

    model_config = SettingsConfigDict(env_prefix="DEVPILOT_", env_file=".env", extra="ignore")
