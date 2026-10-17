"""Runtime base classes and configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from devpilot.domain.result import AgentRunResult
from devpilot.domain.task import DevelopmentTask


class AgentRunner(Protocol):
    """Small evaluation boundary; evaluators do not import a concrete runtime."""

    sandbox: Any
    verifier: Any
    deadline: float | None

    async def run(self, task: DevelopmentTask) -> AgentRunResult: ...


@dataclass
class RuntimeConfig:
    """Configuration for the agent runtime loop.

    Controls loop budgets enforced by the Runtime (design doc §5, §13).
    """

    max_steps: int = 30
    max_test_retries: int = 3
    max_modified_files: int = 10
    max_patch_failures: int = 3
    test_timeout_seconds: int = 120
    max_llm_requests: int = 90
    llm_timeout_seconds: float = 120
    max_run_seconds: float = 1800

    def __post_init__(self) -> None:
        for name in (
            "max_steps",
            "max_modified_files",
            "max_patch_failures",
            "test_timeout_seconds",
            "max_llm_requests",
            "llm_timeout_seconds",
            "max_run_seconds",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_test_retries < 0:
            raise ValueError("max_test_retries must be non-negative")
