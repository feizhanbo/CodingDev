"""Tests for domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
from devpilot.domain.plan import ImplementationPlan, PlanStep
from devpilot.domain.result import AgentRunResult
from devpilot.domain.state import DevPilotState, Observation, TestRun
from devpilot.domain.task import DevelopmentTask


class TestDevelopmentTask:
    def test_creation_with_required_fields(self) -> None:
        task = DevelopmentTask(
            id="T-1",
            title="Add login",
            description="Implement login endpoint",
            acceptance_criteria=["User can log in", "Returns JWT"],
        )
        assert task.id == "T-1"
        assert task.title == "Add login"
        assert task.acceptance_criteria == ["User can log in", "Returns JWT"]

    def test_default_values(self) -> None:
        task = DevelopmentTask(
            id="T-1",
            title="Add login",
            description="Implement login endpoint",
            acceptance_criteria=[],
        )
        assert task.constraints == []
        assert task.metadata == {}

    def test_default_values_are_independent(self) -> None:
        task1 = DevelopmentTask(
            id="T-1", title="A", description="d", acceptance_criteria=[]
        )
        task2 = DevelopmentTask(
            id="T-2", title="B", description="d", acceptance_criteria=[]
        )
        task1.constraints.append("no breaking changes")
        task1.metadata["key"] = "value"
        assert task2.constraints == []
        assert task2.metadata == {}

    def test_serialization_roundtrip(self) -> None:
        task = DevelopmentTask(
            id="T-1",
            title="Add login",
            description="Implement login endpoint",
            acceptance_criteria=["User can log in"],
            constraints=["Do not break existing API"],
            metadata={"priority": "high"},
        )
        data = task.model_dump()
        restored = DevelopmentTask.model_validate(data)
        assert restored == task


class TestPlanStep:
    @pytest.mark.parametrize("status", ["pending", "running", "completed", "failed", "skipped"])
    def test_status_accepts_all_values(self, status: str) -> None:
        step = PlanStep(id=1, description="Do something", status=status)
        assert step.status == status

    def test_default_verification_hint(self) -> None:
        step = PlanStep(id=1, description="Do something", status="pending")
        assert step.verification_hint is None

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlanStep(id=1, description="Do something", status="invalid")

    def test_serialization_roundtrip(self) -> None:
        step = PlanStep(
            id=1, description="Do something", status="completed", verification_hint="Check tests"
        )
        restored = PlanStep.model_validate(step.model_dump())
        assert restored == step


class TestImplementationPlan:
    def test_creation_with_steps(self) -> None:
        steps = [
            PlanStep(id=1, description="A", status="pending"),
            PlanStep(id=2, description="B", status="pending"),
        ]
        plan = ImplementationPlan(goal="Implement feature", steps=steps)
        assert plan.goal == "Implement feature"
        assert len(plan.steps) == 2
        assert plan.revision == 1

    def test_serialization_roundtrip(self) -> None:
        plan = ImplementationPlan(
            goal="Implement feature",
            steps=[PlanStep(id=1, description="A", status="completed")],
            revision=3,
        )
        restored = ImplementationPlan.model_validate(plan.model_dump())
        assert restored == plan


class TestObservation:
    @pytest.mark.parametrize("source", ["tool", "runtime", "verifier"])
    def test_source_accepts_all_values(self, source: str) -> None:
        obs = Observation(
            step_id=1, source=source, name="test", success=True, summary="ok"
        )
        assert obs.source == source

    def test_default_values(self) -> None:
        obs = Observation(
            step_id=1, source="tool", name="test", success=True, summary="ok"
        )
        assert obs.data is None
        assert obs.duration_ms is None

    def test_serialization_roundtrip(self) -> None:
        obs = Observation(
            step_id=1,
            source="runtime",
            name="run_tests",
            success=False,
            summary="2 failures",
            data={"failed": ["test_a"]},
            duration_ms=500,
        )
        restored = Observation.model_validate(obs.model_dump())
        assert restored == obs


class TestTestRun:
    def test_creation(self) -> None:
        run = TestRun(
            run_id="R-1",
            exit_code=0,
            passed=10,
            failed=0,
            duration_ms=1200,
            summary="All passed",
        )
        assert run.run_id == "R-1"
        assert run.exit_code == 0
        assert run.passed == 10
        assert run.log_file is None

    def test_serialization_roundtrip(self) -> None:
        run = TestRun(
            run_id="R-1",
            exit_code=1,
            passed=8,
            failed=2,
            duration_ms=3000,
            summary="2 failures",
            log_file="/tmp/log.txt",
        )
        restored = TestRun.model_validate(run.model_dump())
        assert restored == run


class TestDevPilotState:
    @pytest.mark.parametrize(
        "phase",
        [
            "understanding", "exploring", "planning",
            "implementing", "verifying", "completed", "failed",
        ],
    )
    def test_phase_accepts_all_7_values(self, phase: str) -> None:
        task = DevelopmentTask(
            id="T-1", title="t", description="d", acceptance_criteria=[]
        )
        state = DevPilotState(run_id="R-1", task=task, phase=phase)
        assert state.phase == phase

    def test_default_values(self) -> None:
        task = DevelopmentTask(
            id="T-1", title="t", description="d", acceptance_criteria=[]
        )
        state = DevPilotState(run_id="R-1", task=task, phase="planning")
        assert state.plan is None
        assert state.observations == []
        assert state.modified_files == []
        assert state.test_runs == []
        assert state.current_step == 0
        assert state.total_steps == 0
        assert state.retry_count == 0
        assert state.completion_requested is False

    def test_serialization_roundtrip(self) -> None:
        task = DevelopmentTask(
            id="T-1", title="t", description="d", acceptance_criteria=["c1"]
        )
        plan = ImplementationPlan(
            goal="g", steps=[PlanStep(id=1, description="s", status="completed")]
        )
        obs = Observation(
            step_id=1, source="tool", name="read_file", success=True, summary="ok"
        )
        run = TestRun(
            run_id="tr-1", exit_code=0, duration_ms=100, summary="pass"
        )
        state = DevPilotState(
            run_id="R-1",
            task=task,
            phase="implementing",
            plan=plan,
            observations=[obs],
            modified_files=["src/main.py"],
            test_runs=[run],
            current_step=1,
            total_steps=5,
            retry_count=0,
            completion_requested=False,
        )
        restored = DevPilotState.model_validate(state.model_dump())
        assert restored == state


class TestAgentDecision:
    def test_empty_decision(self) -> None:
        with pytest.raises(ValueError, match="Exactly one"):
            AgentDecision()

    def test_only_action(self) -> None:
        decision = AgentDecision(
            action=ToolAction(tool="read_file", arguments={"path": "/tmp/x"})
        )
        assert decision.action is not None
        assert decision.action.tool == "read_file"
        assert decision.finish is None
        assert decision.plan_update is None

    def test_only_finish(self) -> None:
        decision = AgentDecision(
            finish=FinishIntent(summary="Done", risk="low")
        )
        assert decision.action is None
        assert decision.finish is not None
        assert decision.finish.risk == "low"
        assert decision.plan_update is None

    def test_only_plan_update(self) -> None:
        plan = ImplementationPlan(
            goal="g", steps=[PlanStep(id=1, description="s", status="pending")]
        )
        decision = AgentDecision(plan_update=plan)
        assert decision.action is None
        assert decision.finish is None
        assert decision.plan_update is not None
        assert decision.plan_update.goal == "g"

    def test_action_and_finish(self) -> None:
        with pytest.raises(ValueError, match="Exactly one"):
            AgentDecision(action=ToolAction(tool="run_tests", arguments={}),
                          finish=FinishIntent(summary="Done", risk="medium"))

    def test_all_three(self) -> None:
        with pytest.raises(ValueError, match="Exactly one"):
            AgentDecision(action=ToolAction(tool="apply_patch", arguments={}),
                          finish=FinishIntent(summary="Done", risk="high"),
                          plan_update=ImplementationPlan(goal="g", steps=[]))

    def test_serialization_roundtrip(self) -> None:
        decision = AgentDecision(action=ToolAction(tool="read_file", arguments={"path": "/x"}))
        assert AgentDecision.model_validate(decision.model_dump()) == decision

    def test_finish_invalid_risk_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FinishIntent(summary="x", risk="critical")  # type: ignore[arg-type]


class TestAgentRunResult:
    def test_creation_with_defaults(self) -> None:
        result = AgentRunResult(
            run_id="R-1",
            task_id="T-1",
            status="completed",
            phase="completed",
            total_steps=5,
        )
        assert result.modified_files == []
        assert result.observations == []
        assert result.final_diff is None
        assert result.summary is None
        assert result.risk is None
        assert result.duration_ms is None
        assert result.error is None

    def test_serialization_roundtrip(self) -> None:
        obs = Observation(
            step_id=1, source="tool", name="read_file", success=True, summary="ok"
        )
        result = AgentRunResult(
            run_id="R-1",
            task_id="T-1",
            status="failed",
            phase="verifying",
            total_steps=3,
            modified_files=["a.py"],
            observations=[obs],
            final_diff="diff content",
            summary="Failed at verification",
            risk="high",
            duration_ms=5000,
            error="Tests failed",
        )
        restored = AgentRunResult.model_validate(result.model_dump())
        assert restored == result
