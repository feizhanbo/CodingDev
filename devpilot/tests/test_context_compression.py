"""Tests for context compression in ContextBuilder."""

from __future__ import annotations

from devpilot.domain.plan import ImplementationPlan, PlanStep
from devpilot.domain.state import DevPilotState, Observation
from devpilot.domain.task import DevelopmentTask
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
) -> DevPilotState:
    state = DevPilotState(
        run_id="test-run",
        task=_make_task(),
        phase=phase,  # type: ignore[arg-type]
    )
    if observations:
        state.observations = observations
    return state


def _make_obs(
    step_id: int,
    name: str = "repo.read_file",
    summary: str = "OK",
    success: bool = True,
) -> Observation:
    return Observation(
        step_id=step_id,
        source="tool",
        name=name,
        success=success,
        summary=summary,
    )


def _make_plan() -> ImplementationPlan:
    return ImplementationPlan(
        goal="Implement feature",
        steps=[
            PlanStep(id=1, description="Step 1", status="pending"),
            PlanStep(
                id=2, description="Step 2", status="pending",
                verification_hint="Run tests",
            ),
        ],
    )


class TestShortRunFullObservations:
    """Test that short runs keep full observations."""

    def test_short_run_has_all_observations(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        obs = [_make_obs(i) for i in range(1, 6)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 5

        messages = cb.build(state, "/workspace")
        state_msg = next(m for m in messages if "Current Phase" in m.content)

        assert "Recent Observations" in state_msg.content
        assert "Step 1" in state_msg.content
        assert "Step 5" in state_msg.content
        assert "Progress Summary" not in state_msg.content

    def test_short_run_no_compression_section(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        obs = [_make_obs(i) for i in range(1, 4)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 3

        messages = cb.build(state, "/workspace")
        state_msg = next(m for m in messages if "Current Phase" in m.content)

        assert "Progress Summary" not in state_msg.content


class TestLongRunCompressesOlder:
    """Test that long runs compress older observations."""

    def test_long_run_has_progress_summary(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        obs = [_make_obs(i) for i in range(1, 16)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 15

        messages = cb.build(state, "/workspace")
        state_msg = next(m for m in messages if "Current Phase" in m.content)

        assert "Progress Summary" in state_msg.content
        assert "5 earlier steps" in state_msg.content
        assert "Recent Observations" in state_msg.content
        assert "last 10" in state_msg.content

    def test_older_observations_summarized_format(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        obs = [_make_obs(i) for i in range(1, 16)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 15

        messages = cb.build(state, "/workspace")
        state_msg = next(m for m in messages if "Current Phase" in m.content)

        parts = state_msg.content.split("--- Recent Observations")
        summary_section = parts[0]
        recent_section = parts[1] if len(parts) > 1 else ""

        assert "+ Step" in summary_section
        assert "[repo.read_file]" in recent_section


class TestCompressedShorterThanFull:
    """Test that compressed observations are shorter than full."""

    def test_compressed_observations_truncated(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        long_summary = "x" * 200
        obs = [_make_obs(i, summary=long_summary) for i in range(1, 16)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 15

        messages = cb.build(state, "/workspace")
        state_msg = next(m for m in messages if "Current Phase" in m.content)

        parts = state_msg.content.split("--- Recent Observations")
        summary_section = parts[0]

        assert "..." in summary_section

    def test_full_observations_truncated_at_200(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        long_summary = "x" * 300
        obs = [_make_obs(i, summary=long_summary) for i in range(1, 6)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 5

        messages = cb.build(state, "/workspace")
        state_msg = next(m for m in messages if "Current Phase" in m.content)

        assert "..." in state_msg.content


class TestTaskAlwaysComplete:
    """Test that task/acceptance_criteria are always complete in context."""

    def test_task_complete_in_short_run(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        state = _make_state(phase="exploring")

        messages = cb.build(state, "/workspace")
        task_msg = next(
            m for m in messages if "Add order endpoint" in m.content
        )

        assert "POST /orders" in task_msg.content
        assert "Returns 201" in task_msg.content
        assert "Validates input" in task_msg.content
        assert "No schema changes" in task_msg.content

    def test_task_complete_in_long_run(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        obs = [_make_obs(i) for i in range(1, 20)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 19

        messages = cb.build(state, "/workspace")
        task_msg = next(
            m for m in messages if "Add order endpoint" in m.content
        )

        assert "POST /orders" in task_msg.content
        assert "Returns 201" in task_msg.content
        assert "Validates input" in task_msg.content
        assert "No schema changes" in task_msg.content


class TestPlanAlwaysVisible:
    """Test that plan is always visible in context."""

    def test_plan_visible_short_run(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        state = _make_state(phase="planning")
        state.plan = _make_plan()

        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Implementation Plan" in m.content
        )

        assert "Step 1" in state_msg.content
        assert "Step 2" in state_msg.content
        assert "Verification: Run tests" in state_msg.content

    def test_plan_visible_long_run(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        obs = [_make_obs(i) for i in range(1, 20)]
        state = _make_state(phase="implementing", observations=obs)
        state.total_steps = 19
        state.plan = _make_plan()

        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Implementation Plan" in m.content
        )

        assert "Step 1" in state_msg.content
        assert "Step 2" in state_msg.content


class TestTruncation:
    """Test the _truncate method."""

    def test_truncate_short_text_unchanged(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        assert cb._truncate("short", 100) == "short"

    def test_truncate_long_text_adds_ellipsis(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        long_text = "x" * 200
        result = cb._truncate(long_text, 100)
        assert len(result) == 100
        assert result.endswith("...")
        assert result[:97] == "x" * 97

    def test_truncate_exact_length_unchanged(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        text = "x" * 100
        assert cb._truncate(text, 100) == text

    def test_truncate_one_char_over_adds_ellipsis(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        text = "x" * 101
        result = cb._truncate(text, 100)
        assert len(result) == 100
        assert result.endswith("...")


class TestContextCompression:
    """Test that _compress_context reduces context size."""

    def test_compression_reduces_recent_observations(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        cb.max_context_chars = 1
        obs = [_make_obs(i) for i in range(1, 16)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 15

        messages = cb.build(state, "/workspace")
        state_msg = next(m for m in messages if "Current Phase" in m.content)

        assert "7 earlier steps" in state_msg.content
        assert "last 8" in state_msg.content

    def test_compression_preserves_task(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        cb.max_context_chars = 1
        obs = [_make_obs(i) for i in range(1, 16)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 15

        messages = cb.build(state, "/workspace")
        task_msg = next(
            m for m in messages if "Add order endpoint" in m.content
        )

        assert "POST /orders" in task_msg.content
        assert "Returns 201" in task_msg.content

    def test_compression_preserves_plan(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        cb.max_context_chars = 1
        obs = [_make_obs(i) for i in range(1, 16)]
        state = _make_state(phase="implementing", observations=obs)
        state.total_steps = 15
        state.plan = _make_plan()

        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Implementation Plan" in m.content
        )

        assert "Step 1" in state_msg.content

    def test_no_compression_when_under_budget(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        cb.max_context_chars = 100000
        obs = [_make_obs(i) for i in range(1, 16)]
        state = _make_state(phase="exploring", observations=obs)
        state.total_steps = 15

        messages = cb.build(state, "/workspace")
        state_msg = next(m for m in messages if "Current Phase" in m.content)

        assert "5 earlier steps" in state_msg.content
        assert "last 10" in state_msg.content
