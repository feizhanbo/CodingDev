"""Tests for ImplementationPlan flow in the runtime."""

from __future__ import annotations

import json
from pathlib import Path

from devpilot.agents.developer import DeveloperAgent
from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
from devpilot.domain.plan import ImplementationPlan, PlanStep
from devpilot.domain.task import DevelopmentTask
from devpilot.llm.base import LLMResponse
from devpilot.llm.fake import FakeLLMClient
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.runtime.custom.loop_guard import LoopGuard
from devpilot.runtime.custom.runner import CustomAgentRunner
from devpilot.runtime.custom.state_manager import StateManager
from devpilot.tools import ToolRegistry
from devpilot.tools.code import ApplyPatch, CreateFile
from devpilot.tools.git import GitDiff, GitStatus
from devpilot.tools.repo import ListFiles, ReadFile, SearchCode
from devpilot.tools.test import RunTests
from devpilot.tracing import MetricsCollector, TraceWriter
from devpilot.verification import TaskVerifier
from devpilot.workspace.sandbox import SandboxWorkspace


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _setup_baseline(base: Path) -> None:
    """Create a baseline repo with source files and a passing test."""
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\n")
    _write(base / "test_pass.py", "def test_ok():\n    assert True\n")


def _full_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for tool in (
        ListFiles(), ReadFile(), SearchCode(),
        ApplyPatch(), CreateFile(),
        RunTests(), GitDiff(), GitStatus(),
    ):
        reg.register(tool)
    return reg


def _make_task() -> DevelopmentTask:
    return DevelopmentTask(
        id="DEV-001",
        title="Add order endpoint",
        description="Create POST /orders",
        acceptance_criteria=["Returns 201", "Validates input"],
        constraints=["No schema changes"],
    )


def _make_plan(revision: int = 1) -> ImplementationPlan:
    return ImplementationPlan(
        goal="Implement the feature",
        steps=[
            PlanStep(id=1, description="Read existing code", status="pending"),
            PlanStep(
                id=2, description="Implement changes", status="pending",
                verification_hint="Run pytest",
            ),
        ],
        revision=revision,
    )


def _make_runner(
    responses: list[LLMResponse],
    config: RuntimeConfig,
    baseline: Path,
    tmp_path: Path,
    with_verifier: bool = True,
) -> CustomAgentRunner:
    client = FakeLLMClient(responses)
    registry = _full_registry()
    agent = DeveloperAgent(client, registry)
    sandbox = SandboxWorkspace(
        base_repo_path=str(baseline),
        workspace_root=str(tmp_path / "workspaces"),
        runs_root=str(tmp_path / "runs"),
    )
    state_manager = StateManager(config)
    context_builder = ContextBuilder(config, registry)
    loop_guard = LoopGuard(config)
    verifier = TaskVerifier(config) if with_verifier else None
    trace_writer = TraceWriter(str(tmp_path / "runs"))
    metrics = MetricsCollector()
    return CustomAgentRunner(
        agent=agent,
        registry=registry,
        sandbox=sandbox,
        state_manager=state_manager,
        context_builder=context_builder,
        loop_guard=loop_guard,
        config=config,
        verifier=verifier,
        trace_writer=trace_writer,
        metrics=metrics,
    )


def _resp_action(tool: str, **args: object) -> LLMResponse:
    return LLMResponse(
        decision=AgentDecision(
            action=ToolAction(tool=tool, arguments=dict(args))
        ),
        model="fake",
    )


def _resp_finish(summary: str = "done", risk: str = "low") -> LLMResponse:
    return LLMResponse(
        decision=AgentDecision(
            finish=FinishIntent(summary=summary, risk=risk)  # type: ignore[arg-type]
        ),
        model="fake",
    )


def _resp_with_plan(
    tool: str, plan: ImplementationPlan, **args: object
) -> LLMResponse:
    return LLMResponse(
        decision=AgentDecision(
            action=ToolAction(tool=tool, arguments=dict(args)),
            plan_update=plan,
        ),
        model="fake",
    )


PATCH_MODIFY_APP = (
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1 +1,2 @@\n"
    "-x = 1\n"
    "+x = 1\n"
    "+y = 2\n"
)


def _read_trace_events(runs_dir: Path) -> list[dict]:
    trace_path = runs_dir / "trace.jsonl"
    lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
    return [json.loads(line) for line in lines]


class TestPlanCreation:
    """Test that the agent can create a plan and it's stored in state."""

    async def test_plan_created_trace_emitted(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [
            _resp_action("repo.search_code", query="orders"),
            _resp_with_plan("repo.read_file", _make_plan(1), path="app.py"),
            _resp_with_plan(
                "code.apply_patch", _make_plan(2), patch=PATCH_MODIFY_APP
            ),
            _resp_action("test.run", target="test_pass.py"),
            _resp_finish(summary="All done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        trace_events = _read_trace_events(runs_dir)
        event_types = [e["event"] for e in trace_events]

        assert "plan_created" in event_types
        assert "plan_updated" in event_types

    async def test_plan_stored_in_state(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [
            _resp_action("repo.search_code", query="orders"),
            _resp_with_plan("repo.read_file", _make_plan(1), path="app.py"),
            _resp_with_plan(
                "code.apply_patch", _make_plan(2), patch=PATCH_MODIFY_APP
            ),
            _resp_action("test.run", target="test_pass.py"),
            _resp_finish(summary="done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        state_data = json.loads(
            (runs_dir / "state.json").read_text(encoding="utf-8")
        )
        assert state_data["plan"] is not None
        assert state_data["plan"]["revision"] == 2
        assert len(state_data["plan"]["steps"]) == 2


class TestPlanVisibleInContext:
    """Test that the plan is visible in the context builder output."""

    def test_plan_visible_in_context(self, registry: ToolRegistry) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        state = _make_state_with_plan("planning")

        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Implementation Plan" in m.content
        )
        assert "revision 1" in state_msg.content
        assert "Read existing code" in state_msg.content
        assert "Implement changes" in state_msg.content

    def test_plan_with_verification_hint(
        self, registry: ToolRegistry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        state = _make_state_with_plan("planning")

        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Implementation Plan" in m.content
        )
        assert "Verification: Run pytest" in state_msg.content

    def test_plan_step_status_shown(self, registry: ToolRegistry) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        state = _make_state_with_plan("implementing")
        state.plan = ImplementationPlan(
            goal="Test",
            steps=[
                PlanStep(id=1, description="Done step", status="completed"),
                PlanStep(id=2, description="Pending step", status="pending"),
            ],
        )

        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Implementation Plan" in m.content
        )
        assert "[completed]" in state_msg.content
        assert "[pending]" in state_msg.content


class TestPlanUpdateDuringRepair:
    """Test that the plan can be updated during a repair cycle."""

    async def test_plan_updated_during_repair(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [
            _resp_action("repo.search_code", query="orders"),
            _resp_with_plan("repo.read_file", _make_plan(1), path="app.py"),
            _resp_finish(summary="done", risk="low"),
            _resp_with_plan(
                "code.apply_patch", _make_plan(2), patch=PATCH_MODIFY_APP
            ),
            _resp_action("test.run", target="test_pass.py"),
            _resp_finish(summary="all done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        trace_events = _read_trace_events(runs_dir)
        event_types = [e["event"] for e in trace_events]

        assert "plan_created" in event_types
        assert "plan_updated" in event_types

        state_data = json.loads(
            (runs_dir / "state.json").read_text(encoding="utf-8")
        )
        assert state_data["plan"]["revision"] == 2


class TestPlanTraceEvents:
    """Test plan_created and plan_updated trace event ordering."""

    async def test_plan_created_before_plan_updated(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [
            _resp_action("repo.search_code", query="orders"),
            _resp_with_plan("repo.read_file", _make_plan(1), path="app.py"),
            _resp_with_plan(
                "code.apply_patch", _make_plan(2), patch=PATCH_MODIFY_APP
            ),
            _resp_action("test.run", target="test_pass.py"),
            _resp_finish(summary="done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        trace_events = _read_trace_events(runs_dir)
        event_types = [e["event"] for e in trace_events]

        plan_created_idx = event_types.index("plan_created")
        plan_updated_idx = event_types.index("plan_updated")
        assert plan_created_idx < plan_updated_idx


def _make_state_with_plan(phase: str):
    from devpilot.domain.state import DevPilotState

    state = DevPilotState(
        run_id="test-run",
        task=_make_task(),
        phase=phase,  # type: ignore[arg-type]
    )
    state.plan = _make_plan(1)
    return state
