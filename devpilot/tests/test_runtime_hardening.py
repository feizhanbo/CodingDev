"""Regression tests for audited runtime boundaries."""

import json

import pytest

from devpilot.domain.state import Observation
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.tools.registry import ToolRegistry
from devpilot.verification.verifier import VerificationResult, coverage_for
from tests.runtime.test_runner import (
    _make_runner, _make_task, _resp_action, _resp_finish, _setup_baseline,
)


class ScriptedVerifier:
    deadline = None

    def __init__(self):
        self.calls = 0

    def bind_snapshot(self, *args):
        pass

    async def verify(self, *args):
        self.calls += 1
        return VerificationResult(
            success=self.calls > 1,
            checks=[{"name": "behavior", "passed": self.calls > 1, "message": "missing edge"}],
            failure_reason="missing edge" if self.calls == 1 else None,
        )


async def test_early_rejection_retains_repair_after_passing_tool_test(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner([
        _resp_finish(), _resp_action("test.run"), _resp_finish(),
    ], RuntimeConfig(), base, tmp_path)
    runner.verifier = ScriptedVerifier()
    seen = []
    decide = runner.agent.decide

    async def record(messages):
        seen.append("\n".join(m.content for m in messages))
        return await decide(messages)

    runner.agent.decide = record
    outcome = await runner.run(_make_task())
    result = getattr(outcome, "result", outcome)
    assert result.status == "completed", result.error
    assert "Current Phase: implementing" in seen[1]
    assert "missing edge" in seen[1] and "missing edge" in seen[2]
    state = json.loads((tmp_path / "runs" / result.run_id / "state.json").read_text(encoding="utf-8"))
    assert not state["repair_required"]
    assert not state["repair_sources"]
    assert state["retry_count"] == 1


def test_coverage_does_not_infer_behavior_from_test_success():
    task = _make_task()
    task.acceptance_criteria = ["Returns 201", "Add tests"]
    result = coverage_for(task, [
        {"name": "visible_tests", "passed": True},
        {"name": "required_new_tests", "passed": True},
    ])
    assert [c["status"] for c in result] == ["uncovered", "verified"]


def test_registry_rejects_alias_collision():
    from devpilot.tools.repo.read_file import ReadFile

    registry = ToolRegistry()
    registry.register(ReadFile())
    other = ReadFile()
    other.name = "repo_read_file"
    with pytest.raises(ValueError, match="collision"):
        registry.register(other)


def test_context_hard_limit_preserves_task_and_plan():
    from devpilot.llm.base import ContextBudgetExceeded
    from devpilot.runtime.custom.state_manager import StateManager

    state = StateManager(RuntimeConfig()).create(_make_task())
    state.task.description = "x" * 40000
    builder = ContextBuilder(RuntimeConfig(), ToolRegistry())
    with pytest.raises(ContextBudgetExceeded):
        builder.build(state, ".")
    state.task.description = "important task"
    state.observations = [Observation(
        step_id=i, source="tool", name="repo.read_file", success=True,
        summary="read", data={"content": "x" * 20000, "path": f"{i}.py"},
    ) for i in range(50)]
    messages = builder.build(state, ".")
    assert sum(len(m.content) for m in messages) <= 30000
    assert any("important task" in m.content for m in messages)


async def test_wire_schema_is_counted_before_transport(monkeypatch):
    from devpilot.llm.base import ContextBudgetExceeded, LLMMessage
    from devpilot.llm.config import LLMConfig
    from devpilot.llm.openai import OpenAIClient

    client = OpenAIClient(LLMConfig(_env_file=None, api_key="synthetic", max_context_chars=10))
    calls = []

    async def transport(**kwargs):
        calls.append(kwargs)
        raise AssertionError("Must not dispatch")

    monkeypatch.setattr(client._client.chat.completions, "create", transport)
    try:
        with pytest.raises(ContextBudgetExceeded):
            await client.chat([LLMMessage(role="system", content="short")])
        assert calls == []
    finally:
        await client._client.close()


async def test_oversized_task_does_not_consume_model_request(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner([], RuntimeConfig(), base, tmp_path)
    task = _make_task()
    task.description = "x" * 40000
    result = await runner.run(task)
    assert result.termination_reason == "context_budget_exceeded"
    assert result.budget["llm_requests"] == 0


def test_oversized_latest_plan_is_not_silently_removed():
    from devpilot.domain.plan import ImplementationPlan, PlanStep
    from devpilot.llm.base import ContextBudgetExceeded
    from devpilot.runtime.custom.state_manager import StateManager

    state = StateManager(RuntimeConfig()).create(_make_task())
    state.plan = ImplementationPlan(goal="keep", steps=[PlanStep(id=1, description="p" * 40000, status="pending")])
    with pytest.raises(ContextBudgetExceeded):
        ContextBuilder(RuntimeConfig(), ToolRegistry()).build(state, ".")

