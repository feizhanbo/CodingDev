"""Tests for ContextBuilder."""

from __future__ import annotations

from devpilot.domain.state import DevPilotState, Observation
from devpilot.domain.task import DevelopmentTask
from devpilot.llm.base import LLMMessage
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.tools.registry import ToolRegistry


def _make_task() -> DevelopmentTask:
    return DevelopmentTask(
        id="DEV-001",
        title="Add order endpoint",
        description="Create POST /orders",
        acceptance_criteria=["Returns 201", "Validates input"],
        constraints=["No schema changes"],
    )


def _make_state(
    phase: str = "understanding",
    observations: list[Observation] | None = None,
    modified_files: list[str] | None = None,
) -> DevPilotState:
    state = DevPilotState(
        run_id="test-run",
        task=_make_task(),
        phase=phase,  # type: ignore[arg-type]
    )
    if observations:
        state.observations = observations
    if modified_files:
        state.modified_files = modified_files
    return state


def _make_obs(step_id: int, name: str = "repo.read_file") -> Observation:
    return Observation(
        step_id=step_id,
        source="tool",
        name=name,
        success=True,
        summary="OK",
    )


class TestContextBuilderBuild:
    def test_build_returns_list_of_llm_messages(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        state = _make_state()
        messages = cb.build(state, "/workspace")
        assert isinstance(messages, list)
        assert all(isinstance(m, LLMMessage) for m in messages)
        assert len(messages) >= 3

    def test_system_message_is_first(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        state = _make_state()
        messages = cb.build(state, "/workspace")
        assert messages[0].role == "system"
        assert "DevPilot" in messages[0].content

    def test_tool_schemas_in_system_messages(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        messages = cb.build(_make_state(), "/workspace")
        tool_msg = messages[1]
        assert tool_msg.role == "system"
        assert "repo.read_file" in tool_msg.content
        assert "code.apply_patch" in tool_msg.content

    def test_task_message_contains_title_and_criteria(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        messages = cb.build(_make_state(), "/workspace")
        task_msg = next(
            m for m in messages if "Add order endpoint" in m.content
        )
        assert "POST /orders" in task_msg.content
        assert "Returns 201" in task_msg.content
        assert "No schema changes" in task_msg.content

    def test_state_message_contains_phase_and_step(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(max_steps=30), registry)
        state = _make_state(phase="exploring")
        state.total_steps = 5
        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Current Phase" in m.content
        )
        assert "exploring" in state_msg.content
        assert "5/30" in state_msg.content

    def test_recent_observations_included(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        obs = [_make_obs(i) for i in range(1, 4)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 3
        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Recent Observations" in m.content
        )
        assert "Step 1" in state_msg.content
        assert "Step 3" in state_msg.content

    def test_earlier_observations_summarized(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        obs = [_make_obs(i) for i in range(1, 15)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 14
        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Progress Summary" in m.content
        )
        assert "4 earlier steps" in state_msg.content
        assert "Recent Observations" in state_msg.content

    def test_modified_files_in_state_message(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        state = _make_state(modified_files=["app.py", "src/main.py"])
        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Modified files" in m.content
        )
        assert "app.py" in state_msg.content
        assert "src/main.py" in state_msg.content

    def test_retry_count_in_state_message(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(max_test_retries=3), registry)
        state = _make_state()
        state.retry_count = 2
        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Repair attempts" in m.content
        )
        assert "2/3" in state_msg.content


class TestPhaseInstructions:
    @property
    def _phases(self) -> list[str]:
        return [
            "understanding",
            "exploring",
            "planning",
            "implementing",
            "verifying",
            "completed",
            "failed",
        ]

    def test_different_phases_produce_different_instructions(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        instructions: list[str] = []
        for phase in self._phases:
            state = _make_state(phase=phase)  # type: ignore[arg-type]
            messages = cb.build(state, "/workspace")
            last = messages[-1]
            instructions.append(last.content)
        assert len(set(instructions)) == len(self._phases)

    def test_understanding_instruction_present(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        messages = cb.build(_make_state("understanding"), "/workspace")
        assert any("Analyze the task" in m.content for m in messages)

    def test_implementing_instruction_present(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        messages = cb.build(_make_state("implementing"), "/workspace")
        assert any("Implement the changes" in m.content for m in messages)
