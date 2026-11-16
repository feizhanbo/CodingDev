"""Tests for the Runtime Repair Loop.

Covers the plan_update loop detection in :class:`LoopGuard` and the
end-to-end repair flow in :class:`CustomAgentRunner`:

1. planning phase allows plan_update without guardrail feedback.
2. consecutive plan_update-only decisions are detected and flagged.
3. test fail -> plan_update -> patch -> test pass -> finish completes.
4. test fail -> infinite plan_update -> guard terminates the run.
5. duplicate tool-call detection still works (regression guard).
"""

from __future__ import annotations

import json
from pathlib import Path
from tests.verifier_stub import PassingVerifier

import pytest

from devpilot.agents.developer import DeveloperAgent
from devpilot.domain.decision import (
    AgentDecision,
    FinishIntent,
    ToolAction,
)
from devpilot.domain.plan import ImplementationPlan, PlanStep
from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.llm.base import LLMResponse
from devpilot.llm.fake import FakeLLMClient
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.runtime.custom.loop_guard import (
    DuplicateActionDetected,
    LoopGuard,
)
from devpilot.runtime.custom.runner import CustomAgentRunner
from devpilot.runtime.custom.state_manager import StateManager
from devpilot.tools import ToolRegistry
from devpilot.tools.code import ApplyPatch, CreateFile
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.git import GitDiff, GitStatus
from devpilot.tools.repo import ListFiles, ReadFile, SearchCode
from devpilot.tools.test import RunTests
from devpilot.tracing import MetricsCollector, TraceWriter
from devpilot.workspace.sandbox import SandboxWorkspace

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _setup_baseline(base: Path) -> None:
    """Create a minimal baseline repo (one source file) for the sandbox."""
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\n")


def _make_task() -> DevelopmentTask:
    return DevelopmentTask(
        id="DEV-001",
        title="Fix failing tests",
        description="Repair the failing test suite",
        acceptance_criteria=["Tests pass"],
    )


def _make_decision(
    tool: str | None = "repo.read_file", args: dict | None = None
) -> AgentDecision:
    if tool is None:
        return AgentDecision()
    return AgentDecision(
        action=ToolAction(tool=tool, arguments=args or {"path": "app.py"})
    )


def _make_plan_update(revision: int = 1) -> AgentDecision:
    """A plan_update-only decision (no action, no finish)."""
    return AgentDecision(
        plan_update=ImplementationPlan(
            goal="Fix the failing test",
            steps=[
                PlanStep(
                    id=1,
                    description="Inspect and patch the failing test",
                    status="pending",
                )
            ],
            revision=revision,
        )
    )


def _resp_action(tool: str, **args: object) -> LLMResponse:
    return LLMResponse(
        decision=AgentDecision(
            action=ToolAction(tool=tool, arguments=dict(args))
        ),
        model="fake",
    )


def _resp_plan_update(revision: int = 1) -> LLMResponse:
    return LLMResponse(
        decision=AgentDecision(
            plan_update=ImplementationPlan(
                goal="Fix the failing test",
                steps=[
                    PlanStep(
                        id=1,
                        description="Inspect and patch the failing test",
                        status="pending",
                    )
                ],
                revision=revision,
            )
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


PATCH_FIX_APP = (
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1 +1,2 @@\n"
    "-x = 1\n"
    "+x = 1\n"
    "+y = 2\n"
)


# --------------------------------------------------------------------------- #
# Test doubles for integration tests
# --------------------------------------------------------------------------- #


class _ImplementingStateManager(StateManager):
    """StateManager that boots runs directly into ``implementing``.

    This isolates the repair-loop behaviour from the phase-advancement
    heuristics so the FakeLLMClient sequences can start with ``test.run``.
    """

    def create(
        self, task: DevelopmentTask, run_id: str | None = None
    ) -> DevPilotState:
        rid = run_id if run_id is not None else "run_test"
        return DevPilotState(run_id=rid, task=task, phase="implementing")


class _SpyLoopGuard(LoopGuard):
    """LoopGuard that records the ``repair_required`` flag seen per decision.

    Behaves identically to LoopGuard; it only snapshots the
    ``repair_required`` argument passed to ``check_plan_update_loop`` so the
    test can assert the flag transitions True -> False across the repair.
    """

    def __init__(self, config: RuntimeConfig) -> None:
        super().__init__(config)
        self.repair_required_history: list[bool] = []

    def check_plan_update_loop(
        self,
        decision: AgentDecision,
        phase: str,
        repair_required: bool,
    ) -> dict | None:
        self.repair_required_history.append(repair_required)
        return super().check_plan_update_loop(
            decision, phase, repair_required
        )


class _MockToolRegistry(ToolRegistry):
    """Registry exporting real tool schemas but canned execution results.

    ``test.run`` results are driven by ``test_results`` (one entry per
    call); all other tools return a generic success. This keeps the
    integration tests deterministic and free of real pytest execution.
    """

    def __init__(self, test_results: list[bool]) -> None:
        super().__init__()
        # Register real tools so list_schemas() exports proper schemas for
        # the ContextBuilder / DeveloperAgent.
        for tool in (
            ListFiles(),
            ReadFile(),
            SearchCode(),
            ApplyPatch(),
            CreateFile(),
            RunTests(),
            GitDiff(),
            GitStatus(),
        ):
            self.register(tool)
        self._test_results = list(test_results)
        self._test_index = 0

    async def execute(
        self, action: ToolAction, ctx: ToolContext
    ) -> ToolResult:
        if action.tool == "test.run":
            idx = self._test_index
            self._test_index += 1
            fail = (
                idx < len(self._test_results)
                and self._test_results[idx] is False
            )
            if fail:
                return ToolResult(
                    success=False,
                    error="1 failed",
                    data={
                        "exit_code": 1,
                        "passed": 0,
                        "failed": 1,
                        "summary": "FAILED test_app.py::test_app - assert False",
                        "log_file": "",
                    },
                )
            return ToolResult(
                success=True,
                data={
                    "exit_code": 0,
                    "passed": 1,
                    "failed": 0,
                    "summary": "1 passed",
                    "log_file": "",
                },
            )
        if action.tool == "code.apply_patch":
            return ToolResult(
                success=True, data={"modified_files": ["app.py"]}
            )
        return ToolResult(success=True, data={})


def _make_repair_runner(
    responses: list[LLMResponse],
    config: RuntimeConfig,
    baseline: Path,
    tmp_path: Path,
    test_results: list[bool],
) -> tuple[CustomAgentRunner, _SpyLoopGuard]:
    client = FakeLLMClient(responses)
    registry = _MockToolRegistry(test_results)
    agent = DeveloperAgent(client, registry)
    sandbox = SandboxWorkspace(
        base_repo_path=str(baseline),
        workspace_root=str(tmp_path / "workspaces"),
        runs_root=str(tmp_path / "runs"),
    )
    state_manager = _ImplementingStateManager(config)
    context_builder = ContextBuilder(config, registry)
    guard = _SpyLoopGuard(config)
    trace_writer = TraceWriter(str(tmp_path / "runs"))
    metrics = MetricsCollector()
    runner = CustomAgentRunner(
        agent=agent,
        registry=registry,
        sandbox=sandbox,
        state_manager=state_manager,
        context_builder=context_builder,
        loop_guard=guard,
        config=config,
        verifier=PassingVerifier(),
        trace_writer=trace_writer,
        metrics=metrics,
    )
    return runner, guard


# --------------------------------------------------------------------------- #
# Test 1: planning phase allows plan_update
# --------------------------------------------------------------------------- #


class TestPlanUpdateAllowedInPlanning:
    def test_planning_allows_plan_update_without_violation(self) -> None:
        guard = LoopGuard(RuntimeConfig())
        decision = _make_plan_update()

        # In planning, plan_update is always allowed (no feedback, no raise).
        first = guard.check_plan_update_loop(decision, "planning", False)
        second = guard.check_plan_update_loop(decision, "planning", False)

        assert first is None
        assert second is None


# --------------------------------------------------------------------------- #
# Test 2: consecutive plan_update detected
# --------------------------------------------------------------------------- #


class TestConsecutivePlanUpdateDetected:
    def test_implementing_flags_repeated_plan_update(self) -> None:
        guard = LoopGuard(RuntimeConfig())
        decision = _make_plan_update()

        # implementing phase: 1st allowed, 2nd returns feedback, 3rd feedback
        first = guard.check_plan_update_loop(
            decision, "implementing", False
        )
        assert first is None

        second = guard.check_plan_update_loop(
            decision, "implementing", False
        )
        assert second is not None
        assert second["reason"] == "repeated_plan_update_without_action"
        assert second["count"] == 2

        third = guard.check_plan_update_loop(
            decision, "implementing", False
        )
        assert third is not None
        assert third["reason"] == "repeated_plan_update_without_action"
        assert third["count"] == 3


# --------------------------------------------------------------------------- #
# Test 3: test fail -> plan_update -> patch -> test pass -> finish
# --------------------------------------------------------------------------- #


class TestRepairFlowSucceeds:
    async def test_fail_plan_patch_pass_finish_completes(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [
            _resp_action("test.run", target="test_app.py"),  # 1. fail
            _resp_plan_update(),  # 2. plan_update (allowed, single)
            _resp_action("code.apply_patch", patch=PATCH_FIX_APP),  # 3. patch
            _resp_action("test.run", target="test_app.py"),  # 4. pass
            _resp_finish(summary="done", risk="low"),  # 5. finish
        ]
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        runner, guard = _make_repair_runner(
            responses, config, baseline, tmp_path,
            test_results=[False, True],
        )

        result = await runner.run(_make_task())

        # Run completes successfully.
        assert result.status == "completed"
        assert result.error is None

        # repair_required transitioned True (after fail) -> False (after pass).
        # The spy records repair_required at each decision in call order:
        # [False(initial), True(after fail), True, True, False(after pass)]
        history = guard.repair_required_history
        assert history[1] is True  # decision after the first test failure
        assert history[-1] is False  # decision after the test pass

        # Only one plan_update after the fail is allowed -> no guard feedback.
        feedback_obs = [
            o for o in result.observations
            if o.name == "guardrail_feedback"
        ]
        assert feedback_obs == []


# --------------------------------------------------------------------------- #
# Test 4: test fail -> infinite plan_update -> guard terminates
# --------------------------------------------------------------------------- #


class TestInfinitePlanUpdateTerminated:
    async def test_repeated_plan_update_during_repair_terminates(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        plan = _resp_plan_update()
        responses = [
            _resp_action("test.run", target="test_app.py"),  # 1. fail
            plan, plan, plan, plan, plan,  # 2-6. plan_update x5
        ]
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        runner, _guard = _make_repair_runner(
            responses, config, baseline, tmp_path,
            test_results=[False],
        )

        result = await runner.run(_make_task())

        # Run must terminate (not loop forever) with a failed status.
        assert result.status == "failed"
        assert result.error is not None
        assert "plan_update" in result.error

        # guardrail_feedback Observation was injected before termination.
        feedback_obs = [
            o for o in result.observations
            if o.name == "guardrail_feedback"
        ]
        assert len(feedback_obs) >= 1

        # Trace includes a guardrail_triggered event.
        trace_path = (
            Path(runner.sandbox.runs_root) / result.run_id / "trace.jsonl"
        )
        assert trace_path.is_file()
        lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
        events = [json.loads(line)["event"] for line in lines]
        assert "guardrail_triggered" in events


# --------------------------------------------------------------------------- #
# Test 5: duplicate tool-call detection still works (regression)
# --------------------------------------------------------------------------- #


class TestDuplicateActionRegression:
    def test_six_consecutive_identical_raises(self) -> None:
        guard = LoopGuard(RuntimeConfig())
        d = _make_decision("repo.read_file", {"path": "app.py"})

        # First five consecutive identical calls are tolerated.
        for _ in range(5):
            guard.check_duplicate_action(d)

        # The sixth consecutive identical call triggers the guardrail.
        with pytest.raises(
            DuplicateActionDetected, match="repo.read_file"
        ):
            guard.check_duplicate_action(d)
