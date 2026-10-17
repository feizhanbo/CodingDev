"""Tool context and result models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolContext(BaseModel):
    """Runtime context shared by every tool invocation.

    ``workspace_root`` is the absolute path to the active workspace (the
    repository copy the agent is allowed to read/modify), **not** the
    DevPilot project root.
    """

    workspace_root: str
    run_id: str
    trusted_root: str | None = None
    artifacts_dir: str | None = None
    test_python: str | None = None
    test_timeout_seconds: float | None = None
    deadline: float | None = None
    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolResult(BaseModel):
    """The outcome of a tool execution."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int | None = None
