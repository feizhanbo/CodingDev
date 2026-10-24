"""One configuration entry point for CLI runs and evaluations."""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from devpilot.llm.config import LLMConfig
from devpilot.runtime.base import RuntimeConfig
from devpilot.workspace.config import WorkspaceConfig


class Settings(BaseSettings):
    """Explicit values > environment > dotenv > defaults.

    Paths are relative to the caller's working directory. Packaged benchmark
    resources are resolved separately, never relative to that directory.
    """

    model_config = SettingsConfigDict(
        env_prefix="DEVPILOT_",
        env_file=".env",
        extra="ignore",
        allow_inf_nan=False,
    )

    model: str = "gpt-4o"
    api_key: str = Field(default="", repr=False)
    base_url: str | None = None
    max_tokens: int = Field(default=4096, gt=0)
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_steps: int = Field(default=30, gt=0)
    max_test_retries: int = Field(default=3, ge=0)
    max_modified_files: int = Field(default=10, gt=0)
    max_patch_failures: int = Field(default=3, gt=0)
    test_timeout_seconds: int = Field(default=120, gt=0)
    max_test_output_bytes: int = Field(default=2097152, gt=0)
    max_llm_requests: int = Field(default=90, gt=0)
    llm_timeout_seconds: float = Field(default=120, gt=0)
    max_run_seconds: float = Field(default=1800, gt=0)
    workspace_max_bytes: int = Field(default=268435456, gt=0)
    workspace_total_max_bytes: int = Field(default=2147483648, gt=0)
    run_artifacts_max_bytes: int = Field(default=536870912, gt=0)
    runs_total_max_bytes: int = Field(default=4294967296, gt=0)
    test_python: str = sys.executable
    max_context_chars: int = Field(default=30000, gt=0)
    tool_timeout_seconds: int = Field(default=120, gt=0)
    max_tool_output_bytes: int = Field(default=2097152, gt=0)
    preparation_timeout_seconds: int = Field(default=120, gt=0)
    evaluation_timeout_seconds: int = Field(default=120, gt=0)
    diagnostic_reserve_bytes: int = Field(default=8388608, gt=0)
    network_access: bool = False
    workspace_root: str = "./workspaces"
    runs_root: str = "./runs"
    base_repo: str = "../shopflow-order-service"

    @field_validator("test_python")
    @classmethod
    def absolute_interpreter(cls, value: str) -> str:
        return str(Path(value).resolve()) if "/" in value or "\\" in value else value

    def runtime_config(self) -> RuntimeConfig:
        return RuntimeConfig(
            **{name: getattr(self, name) for name in RuntimeConfig.__dataclass_fields__}
        )

    def llm_config(self) -> LLMConfig:
        return LLMConfig(
            _env_file=None, **{name: getattr(self, name) for name in LLMConfig.model_fields}
        )

    def workspace_config(self) -> WorkspaceConfig:
        return WorkspaceConfig(
            _env_file=None, **{name: getattr(self, name) for name in WorkspaceConfig.model_fields}
        )

    def public_snapshot(self) -> dict:
        """Do not persist credentials with run artifacts."""
        return self.model_dump(exclude={"api_key", "base_url"})
