"""Tests for StateManager."""

from __future__ import annotations

import pytest

from devpilot.domain.state import Observation
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.state_manager import StateManager
from devpilot.tools.context import ToolResult


def _make_task() -> DevelopmentTask:
    return DevelopmentTask(
        id="DEV-001",
        title="Add order creation endpoint",
        description="Create a POST /orders endpoint",
        acceptance_criteria=["Returns 201 on success", "Validates input"],
        constraints=["Do not change response schema"],
    )


def _make_observation(step_id: int = 1) -> Observation:
    return Observation(
        step_id=step_id,
        source="tool",
        name="repo.read_file",
        success=True,
        summary="OK",
    )


class TestStateManagerCreate:
    def test_create_returns_valid_state(self) -> None:
        sm = StateManager(RuntimeConfig())
        task = _make_task()
        state = sm.create(task)
        assert state.task == task
        assert state.phase == "understanding"
        assert state.run_id.startswith("run_")
        assert state.current_step == 0
        assert state.total_steps == 0
        assert state.observations == []
        assert state.modified_files == []
        assert state.completion_requested is False

    def test_create_with_explicit_run_id(self) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task(), run_id="custom-123")
        assert state.run_id == "custom-123"

    def test_create_generates_unique_run_ids(self) -> None:
        sm = StateManager(RuntimeConfig())
        task = _make_task()
        s1 = sm.create(task)
        s2 = sm.create(task)
        assert s1.run_id != s2.run_id


class TestStateManagerTransitions:
    @pytest.mark.parametrize(
        ("from_phase", "to_phase"),
        [
            ("understanding", "exploring"),
            ("understanding", "completed"),
            ("exploring", "planning"),
            ("exploring", "exploring"),
            ("exploring", "completed"),
            ("planning", "implementing"),
            ("planning", "completed"),
            ("implementing", "verifying"),
            ("implementing", "completed"),
            ("verifying", "completed"),
            ("verifying", "implementing"),
            ("verifying", "planning"),
        ],
    )
    def test_valid_transitions(self, from_phase: str, to_phase: str) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task())
        state.phase = from_phase  # type: ignore[assignment]
        sm.transition_phase(state, to_phase)
        assert state.phase == to_phase

    @pytest.mark.parametrize(
        ("from_phase", "to_phase"),
        [
            ("understanding", "planning"),
            ("understanding", "implementing"),
            ("planning", "exploring"),
            ("implementing", "planning"),
            ("completed", "exploring"),
            ("failed", "understanding"),
        ],
    )
    def test_invalid_transitions_raise(
        self, from_phase: str, to_phase: str
    ) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task())
        state.phase = from_phase  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Invalid phase transition"):
            sm.transition_phase(state, to_phase)

    def test_any_phase_can_fail(self) -> None:
        sm = StateManager(RuntimeConfig())
        for phase in (
            "understanding",
            "exploring",
            "planning",
            "implementing",
            "verifying",
        ):
            state = sm.create(_make_task())
            state.phase = phase  # type: ignore[assignment]
            sm.transition_phase(state, "failed")
            assert state.phase == "failed"


class TestStateManagerObservations:
    def test_add_observation_increments_steps(self) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task())
        sm.add_observation(state, _make_observation(1))
        assert state.current_step == 1
        assert state.total_steps == 1
        assert len(state.observations) == 1
        sm.add_observation(state, _make_observation(2))
        assert state.current_step == 2
        assert state.total_steps == 2
        assert len(state.observations) == 2

    def test_apply_tool_result_adds_observation(self) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task())
        result = ToolResult(success=True, data={"path": "app.py"})
        sm.apply_tool_result(state, result, "repo.read_file", 50)
        assert len(state.observations) == 1
        obs = state.observations[0]
        assert obs.name == "repo.read_file"
        assert obs.success is True
        assert obs.summary == "OK"
        assert obs.duration_ms == 50
        assert obs.step_id == 1

    def test_apply_tool_result_adds_modified_files(self) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task())
        result = ToolResult(
            success=True,
            data={"modified_files": ["app.py", "src/main.py"]},
        )
        sm.apply_tool_result(state, result, "code.apply_patch", 30)
        assert "app.py" in state.modified_files
        assert "src/main.py" in state.modified_files

    def test_apply_tool_result_dedup_modified_files(self) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task())
        result = ToolResult(
            success=True,
            data={"modified_files": ["app.py"]},
        )
        sm.apply_tool_result(state, result, "code.apply_patch", 10)
        sm.apply_tool_result(state, result, "code.apply_patch", 10)
        assert state.modified_files == ["app.py"]

    def test_apply_tool_result_failure_observation(self) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task())
        result = ToolResult(success=False, error="file not found")
        sm.apply_tool_result(state, result, "repo.read_file", 5)
        obs = state.observations[0]
        assert obs.success is False
        assert obs.summary == "file not found"


class TestStateManagerSerialize:
    def test_serialize_deserialize_roundtrip(self) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task(), run_id="test-rt")
        sm.add_observation(state, _make_observation(1))
        state.modified_files = ["app.py"]
        json_str = sm.serialize(state)
        restored = sm.deserialize(json_str)
        assert restored.run_id == "test-rt"
        assert restored.phase == "understanding"
        assert restored.total_steps == 1
        assert len(restored.observations) == 1
        assert restored.modified_files == ["app.py"]

    def test_serialize_returns_json_string(self) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task(), run_id="json-1")
        json_str = sm.serialize(state)
        assert isinstance(json_str, str)
        assert '"run_id"' in json_str
        assert "json-1" in json_str


class TestStateManagerCompletion:
    def test_request_completion(self) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task())
        assert state.completion_requested is False
        sm.request_completion(state)
        assert state.completion_requested is True

    def test_increment_retry(self) -> None:
        sm = StateManager(RuntimeConfig())
        state = sm.create(_make_task())
        assert state.retry_count == 0
        sm.increment_retry(state)
        assert state.retry_count == 1
        sm.increment_retry(state)
        assert state.retry_count == 2
