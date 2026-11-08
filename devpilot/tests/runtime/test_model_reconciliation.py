"""Reconcile effects newer than a graph checkpoint without new provider calls."""

from types import SimpleNamespace

import pytest

from devpilot.domain.decision import AgentDecision
from devpilot.llm.base import LLMMessage
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.budget import RunBudget
from devpilot.runtime.langgraph.operations import ManualRecoveryRequired
from devpilot.runtime.langgraph.runner import LangGraphAgentRunner
from devpilot.runtime.shared.session import RunSession
from devpilot.tracing import MetricsCollector
from devpilot.workspace.sandbox import SandboxWorkspace


@pytest.fixture
def case(tmp_path):
    runner = LangGraphAgentRunner.__new__(LangGraphAgentRunner)
    runner.config = RuntimeConfig()
    runner._trace_failure = None
    runner.budget_service = RunBudget.start(runner.config)
    runner.session = RunSession(runner.budget_service)
    runner.deadline = runner.budget_service.deadline
    runner.deadline_at = runner.budget_service.deadline_at
    runner.metrics = MetricsCollector()
    runner.agent = SimpleNamespace(last_request=None)
    runner.sandbox = SandboxWorkspace(str(tmp_path), str(tmp_path / "ws"), str(tmp_path / "runs"))
    state = SimpleNamespace(run_id="run", total_steps=1)
    return runner, state, [LLMMessage(role="user", content="Fix addition")]


def rewind(runner):
    runner.request_count = runner.attempts_in_turn = 0
    runner.metrics = MetricsCollector()


async def test_completed_decision_reused_without_provider(case):
    runner, state, messages = case
    decision = AgentDecision(finish={"summary": "done", "risk": "low"})
    runner.request_count = runner.attempts_in_turn = 1
    runner._begin_model_request(state, messages)
    runner.metrics.record_llm_request({"total_tokens": 42, "status": "success"})
    runner._end_model_request(state, decision)
    original_deadline = runner.budget_service.deadline
    rewind(runner)
    assert await runner.decide_step(state, messages) == decision
    assert runner.request_count == 1
    assert runner.metrics.tokens_used == 42
    assert runner.budget_service.deadline <= original_deadline


def test_prepared_request_charge_is_preserved_exactly_once(case):
    runner, state, messages = case
    runner.request_count = runner.attempts_in_turn = 1
    runner._begin_model_request(state, messages)
    rewind(runner)
    assert runner._reconcile_model_requests(state, messages) is None
    assert runner._reconcile_model_requests(state, messages) is None
    assert runner.request_count == runner.attempts_in_turn == 1
    assert len(runner.metrics.llm_requests) == 1
    assert runner.metrics.llm_requests[0]["total_tokens"] is None


def test_context_mismatch_refused_before_accounting_mutation(case):
    runner, state, messages = case
    runner.request_count = runner.attempts_in_turn = 1
    runner._begin_model_request(state, messages)
    rewind(runner)
    with pytest.raises(ManualRecoveryRequired, match="interrupted turn"):
        runner._reconcile_model_requests(state, [LLMMessage(role="user", content="Different")])
    assert runner.request_count == 0


def test_budget_origin_mismatch_refused(case):
    runner, state, messages = case
    runner.request_count = runner.attempts_in_turn = 1
    runner._begin_model_request(state, messages)
    rewind(runner)
    runner.budget_service.deadline_at += 1
    with pytest.raises(ManualRecoveryRequired, match="budget origin"):
        runner._reconcile_model_requests(state, messages)


async def test_three_interrupted_attempts_do_not_reset_retry_limit(case):
    runner, state, messages = case
    for number in range(1, 4):
        runner.request_count = runner.attempts_in_turn = number
        runner._begin_model_request(state, messages)
    rewind(runner)
    with pytest.raises(Exception, match="interrupted_model_retries_exhausted"):
        await runner.decide_step(state, messages)
    assert runner.request_count == 3


def test_completed_unknown_request_keeps_usage_unknown(case):
    runner, state, messages = case
    runner.request_count = runner.attempts_in_turn = 1
    runner._begin_model_request(state, messages)
    runner._end_model_request(state, None)
    rewind(runner)
    assert runner._reconcile_model_requests(state, messages) is None
    assert runner.metrics.to_dict()["tokens"] is None
    assert runner.metrics.to_dict()["llm_unknown_usage_requests"] == 1
    assert runner.request_count == 1
