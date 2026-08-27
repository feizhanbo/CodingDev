"""Loop guard for the custom runtime."""

from __future__ import annotations

import json

from devpilot.domain.decision import AgentDecision
from devpilot.domain.state import DevPilotState
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.context import ToolResult

MAX_MODIFIED_FILES = 10


class GuardrailViolation(Exception):
    """Raised when a guardrail is violated."""


class MaxStepsExceeded(GuardrailViolation):
    """Agent exceeded the maximum number of steps."""


class MaxRetriesExceeded(GuardrailViolation):
    """Agent exceeded the maximum number of test retries."""


class DuplicateActionDetected(GuardrailViolation):
    """Agent repeated the same tool call too many times."""


class MaxModifiedFilesExceeded(GuardrailViolation):
    """Agent modified more files than allowed."""


class LoopGuard:
    """Enforces runtime guardrails: step limits, retry limits, duplicate actions."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self._recent_tool_calls: list[str] = []

    def check_max_steps(self, state: DevPilotState) -> None:
        """Check if max steps exceeded. Raise MaxStepsExceeded if so."""
        if state.total_steps >= self.config.max_steps:
            raise MaxStepsExceeded(
                f"Exceeded max_steps={self.config.max_steps}"
            )

    def check_test_retries(self, state: DevPilotState) -> None:
        """Check if max test retries exceeded."""
        if state.retry_count >= self.config.max_test_retries:
            raise MaxRetriesExceeded(
                f"Exceeded max_test_retries={self.config.max_test_retries}"
            )

    def check_duplicate_action(self, decision: AgentDecision) -> None:
        """Check for repeated identical tool calls.

        After 4 consecutive identical tool+args, raise DuplicateActionDetected.
        """
        if not decision.action:
            return
        key = f"{decision.action.tool}:{json.dumps(decision.action.arguments, sort_keys=True)}"
        self._recent_tool_calls.append(key)
        if len(self._recent_tool_calls) > 4:
            self._recent_tool_calls = self._recent_tool_calls[-4:]
        if len(self._recent_tool_calls) >= 4:
            last_four = self._recent_tool_calls[-4:]
            if all(k == last_four[-1] for k in last_four):
                raise DuplicateActionDetected(
                    f"Repeated identical tool call: {decision.action.tool}"
                )

    def check_modified_files(self, state: DevPilotState) -> None:
        """Check if max modified files exceeded."""
        if len(state.modified_files) > MAX_MODIFIED_FILES:
            raise MaxModifiedFilesExceeded(
                f"Exceeded max_modified_files={MAX_MODIFIED_FILES}"
            )

    def inspect(
        self, state: DevPilotState, decision: AgentDecision, result: ToolResult
    ) -> None:
        """Run all guardrail checks after a tool execution."""
        self.check_max_steps(state)
        self.check_duplicate_action(decision)
        self.check_modified_files(state)
