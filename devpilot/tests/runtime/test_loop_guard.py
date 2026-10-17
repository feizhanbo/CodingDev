"""Tests for LoopGuard."""

from __future__ import annotations

import pytest

from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.loop_guard import (
    DuplicateActionDetected,
    LoopGuard,
    MaxModifiedFilesExceeded,
    MaxRetriesExceeded,
    MaxStepsExceeded,
)
from devpilot.tools.context import ToolResult


def _make_task() -> DevelopmentTask:
    return DevelopmentTask(
        id="DEV-001",
        title="Test task",
        description="desc",
        acceptance_criteria=["c1"],
    )


def _make_state(total_steps: int = 0, retry_count: int = 0) -> DevPilotState:
    state = DevPilotState(
        run_id="test",
        task=_make_task(),
        phase="exploring",
    )
    state.total_steps = total_steps
    state.retry_count = retry_count
    return state


def _make_decision(
    tool: str | None = "repo.read_file", args: dict | None = None
) -> AgentDecision:
    if tool is None:
        return AgentDecision(finish=FinishIntent(summary="done", risk="low"))
    return AgentDecision(
        action=ToolAction(tool=tool, arguments=args or {"path": "app.py"})
    )


class TestCheckMaxSteps:
    def test_ok_under_limit(self) -> None:
        guard = LoopGuard(RuntimeConfig(max_steps=10))
        state = _make_state(total_steps=5)
        guard.check_max_steps(state)

    def test_raises_at_limit(self) -> None:
        guard = LoopGuard(RuntimeConfig(max_steps=10))
        state = _make_state(total_steps=10)
        with pytest.raises(MaxStepsExceeded, match="max_steps=10"):
            guard.check_max_steps(state)

    def test_raises_over_limit(self) -> None:
        guard = LoopGuard(RuntimeConfig(max_steps=5))
        state = _make_state(total_steps=100)
        with pytest.raises(MaxStepsExceeded):
            guard.check_max_steps(state)


class TestCheckTestRetries:
    def test_ok_under_limit(self) -> None:
        guard = LoopGuard(RuntimeConfig(max_test_retries=3))
        state = _make_state(retry_count=2)
        guard.check_test_retries(state)

    def test_raises_at_limit(self) -> None:
        guard = LoopGuard(RuntimeConfig(max_test_retries=3))
        state = _make_state(retry_count=3)
        with pytest.raises(MaxRetriesExceeded, match="max_test_retries=3"):
            guard.check_test_retries(state)


class TestCheckDuplicateAction:
    def test_no_raise_for_different_actions(self) -> None:
        guard = LoopGuard(RuntimeConfig())
        guard.check_duplicate_action(_make_decision("repo.read_file", {"path": "a"}))
        guard.check_duplicate_action(_make_decision("repo.read_file", {"path": "b"}))
        guard.check_duplicate_action(_make_decision("repo.read_file", {"path": "c"}))
        guard.check_duplicate_action(_make_decision("repo.read_file", {"path": "d"}))

    def test_raises_on_six_consecutive_identical(self) -> None:
        guard = LoopGuard(RuntimeConfig())
        d = _make_decision("repo.read_file", {"path": "app.py"})
        for _ in range(5):
            guard.check_duplicate_action(d)
        with pytest.raises(DuplicateActionDetected, match="repo.read_file"):
            guard.check_duplicate_action(d)

    def test_no_raise_when_pattern_breaks(self) -> None:
        guard = LoopGuard(RuntimeConfig())
        d1 = _make_decision("repo.read_file", {"path": "a"})
        d2 = _make_decision("repo.read_file", {"path": "b"})
        guard.check_duplicate_action(d1)
        guard.check_duplicate_action(d1)
        guard.check_duplicate_action(d1)
        guard.check_duplicate_action(d2)
        guard.check_duplicate_action(d2)

    def test_no_action_skips_check(self) -> None:
        guard = LoopGuard(RuntimeConfig())
        guard.check_duplicate_action(AgentDecision(finish=FinishIntent(summary="done", risk="low")))
        assert len(guard._recent_tool_calls) == 0


class TestCheckModifiedFiles:
    def test_ok_under_limit(self) -> None:
        guard = LoopGuard(RuntimeConfig())
        state = _make_state()
        state.modified_files = [f"file_{i}.py" for i in range(10)]
        guard.check_modified_files(state)

    def test_raises_over_limit(self) -> None:
        guard = LoopGuard(RuntimeConfig())
        state = _make_state()
        state.modified_files = [f"file_{i}.py" for i in range(11)]
        with pytest.raises(MaxModifiedFilesExceeded, match="max_modified_files"):
            guard.check_modified_files(state)


class TestInspect:
    def test_inspect_runs_all_checks_when_ok(self) -> None:
        guard = LoopGuard(RuntimeConfig(max_steps=30))
        state = _make_state(total_steps=5)
        decision = _make_decision("repo.read_file", {"path": "a"})
        result = ToolResult(success=True)
        guard.inspect(state, decision, result)

    def test_inspect_raises_max_steps(self) -> None:
        guard = LoopGuard(RuntimeConfig(max_steps=5))
        state = _make_state(total_steps=5)
        decision = _make_decision()
        result = ToolResult(success=True)
        with pytest.raises(MaxStepsExceeded):
            guard.inspect(state, decision, result)

    def test_inspect_raises_duplicate(self) -> None:
        guard = LoopGuard(RuntimeConfig(max_steps=30))
        state = _make_state(total_steps=0)
        d = _make_decision("repo.read_file", {"path": "x"})
        result = ToolResult(success=True)
        for _ in range(5):
            guard.inspect(state, d, result)
        with pytest.raises(DuplicateActionDetected):
            guard.inspect(state, d, result)
