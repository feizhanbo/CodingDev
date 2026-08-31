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


def _decision_type(decision: AgentDecision) -> str:
    """Classify a decision into a coarse type for loop fingerprinting."""
    if decision.finish:
        return "finish"
    if decision.action:
        return "action"
    if decision.plan_update:
        return "plan_update"
    return "empty"


class LoopGuard:
    """Enforces runtime guardrails: step limits, retry limits, duplicate actions."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self._recent_tool_calls: list[str] = []
        # Decision-level guard state.
        self.last_decision_type: str | None = None
        self.same_decision_count: int = 0
        self.consecutive_plan_update_count: int = 0
        self.consecutive_no_action_count: int = 0
        self.last_action_fingerprint: str | None = None

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

        After 6 consecutive identical tool+args, raise DuplicateActionDetected.
        """
        if not decision.action:
            return
        key = f"{decision.action.tool}:{json.dumps(decision.action.arguments, sort_keys=True)}"
        self._recent_tool_calls.append(key)
        if len(self._recent_tool_calls) > 6:
            self._recent_tool_calls = self._recent_tool_calls[-6:]
        if len(self._recent_tool_calls) >= 6:
            last_six = self._recent_tool_calls[-6:]
            if all(k == last_six[-1] for k in last_six):
                raise DuplicateActionDetected(
                    f"Repeated identical tool call: {decision.action.tool}"
                )

    def check_plan_update_loop(
        self,
        decision: AgentDecision,
        phase: str,
        repair_required: bool,
    ) -> dict | None:
        """Detect repeated plan_update decisions without concrete action.

        Returns a feedback dict when a soft threshold is reached and raises
        GuardrailViolation when a hard threshold is exceeded.
        """
        dtype = _decision_type(decision)

        if dtype == self.last_decision_type:
            self.same_decision_count += 1
        else:
            self.same_decision_count = 1
        self.last_decision_type = dtype

        # Concrete action: reset the no-action / plan_update streaks.
        if decision.action:
            self.consecutive_plan_update_count = 0
            self.consecutive_no_action_count = 0
            self.last_action_fingerprint = (
                f"{decision.action.tool}:"
                f"{json.dumps(decision.action.arguments, sort_keys=True)}"
            )
            return None

        is_plan_update_only = dtype == "plan_update"
        if is_plan_update_only:
            self.consecutive_plan_update_count += 1
            self.consecutive_no_action_count += 1

        # planning phase: always allow plan updates.
        if phase == "planning":
            return None

        if is_plan_update_only:
            if phase == "implementing" and self.consecutive_plan_update_count >= 2:
                return {
                    "reason": "repeated_plan_update_without_action",
                    "count": self.consecutive_plan_update_count,
                    "phase": phase,
                    "required_next_behavior": "take_concrete_action",
                }
            if phase == "verifying" and repair_required:
                if self.consecutive_plan_update_count >= 3:
                    raise GuardrailViolation(
                        "Exceeded max consecutive plan_update "
                        "without action during repair"
                    )
                if self.consecutive_plan_update_count == 2:
                    return {
                        "reason": "repeated_plan_update_during_repair",
                        "count": 2,
                        "phase": phase,
                        "required_next_behavior": "take_concrete_action",
                        "message": (
                            "The previous test still fails. Do not only revise "
                            "the plan. Take a concrete action to inspect or "
                            "modify the implementation."
                        ),
                    }
            if phase == "exploring" and self.consecutive_plan_update_count >= 3:
                return {
                    "reason": "repeated_plan_update_without_action",
                    "count": self.consecutive_plan_update_count,
                    "phase": phase,
                    "required_next_behavior": "take_concrete_action",
                }

        # Safety net: too many consecutive decisions without action.
        if self.consecutive_no_action_count >= 5:
            raise GuardrailViolation(
                "Too many consecutive decisions without action"
            )

        return None

    def reset_repair_state(self) -> None:
        """Reset repair-related guard state after a concrete repair action."""
        self.consecutive_plan_update_count = 0

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
