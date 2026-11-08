"""Durable model admission failures are never provider retries."""

import asyncio
from types import SimpleNamespace

import pytest

from devpilot.domain.decision import AgentDecision
from devpilot.runtime.langgraph.operations import OperationJournal
from devpilot.runtime.langgraph.runner import LangGraphAgentRunner
from devpilot.runtime.shared.steps import ExecutionSteps
from devpilot.tracing import MetricsCollector
from devpilot.workspace.sandbox import SandboxWorkspace


class Harness(ExecutionSteps):
    _begin_model_request = LangGraphAgentRunner._begin_model_request
    _end_model_request = LangGraphAgentRunner._end_model_request

    def __init__(self, tmp_path):
        self.request_count = self.attempts_in_turn = self.calls = 0
        self.config = SimpleNamespace(max_llm_requests=5, llm_timeout_seconds=10)
        self.agent = SimpleNamespace(last_request=None)
        self.registry = None
        self.decisions = self
        self.metrics = MetricsCollector()
        self.budget_service = SimpleNamespace(snapshot=lambda: {"elapsed_seconds": 1})
        self.sandbox = SandboxWorkspace(str(tmp_path), str(tmp_path / "ws"), str(tmp_path / "runs"))

    def _remaining(self):
        return 10

    def _checkpoint(self, *args):
        pass

    async def decide(self, *args):
        self.calls += 1
        if self.calls < 3:
            raise ValueError("bad response")
        return AgentDecision(finish={"summary": "done", "risk": "low"})


@pytest.fixture
def state():
    return SimpleNamespace(run_id="ledger", total_steps=0, phase="analyzing")


async def test_model_retries_have_distinct_charged_receipts(tmp_path, state):
    runner = Harness(tmp_path)
    await runner.decide_step(state, [])
    journal = OperationJournal(runner.sandbox, state.run_id)
    for number in range(1, 4):
        receipt = journal.read(f"ledger:model:{number}")
        assert receipt.stage == "completed"
        assert receipt.admission["request_count"] == number
        assert receipt.output["request_count"] == number
        assert (receipt.output["decision"] is not None) == (number == 3)
    assert runner.calls == runner.request_count == 3


async def test_admission_failure_never_dispatches(tmp_path, state, monkeypatch):
    runner = Harness(tmp_path)

    def fail(*args):
        raise OSError("full")

    monkeypatch.setattr(runner.sandbox, "save_artifact", fail)
    with pytest.raises(OSError, match="full"):
        await runner.decide_step(state, [])
    assert runner.calls == 0
    assert runner.request_count == 1


async def test_result_receipt_failure_never_retries(tmp_path, state, monkeypatch):
    runner = Harness(tmp_path)

    def fail(*args):
        raise OSError("full")

    monkeypatch.setattr(OperationJournal, "complete", fail)
    with pytest.raises(OSError, match="full"):
        await runner.decide_step(state, [])
    assert runner.calls == runner.request_count == 1
    assert OperationJournal(runner.sandbox, "ledger").read("ledger:model:1").stage == "prepared"


async def test_checkpoint_failure_keeps_precharge_without_dispatch(tmp_path, state, monkeypatch):
    runner = Harness(tmp_path)

    def fail(*args):
        raise OSError("checkpoint failed")

    monkeypatch.setattr(runner, "_checkpoint", fail)
    with pytest.raises(OSError, match="checkpoint failed"):
        await runner.decide_step(state, [])
    assert runner.calls == 0
    receipt = OperationJournal(runner.sandbox, "ledger").read("ledger:model:1")
    assert receipt.admission["request_count"] == 1
    assert receipt.stage == "prepared"


async def test_cancelled_request_preserves_charge_and_unknown_usage(tmp_path, state, monkeypatch):
    runner = Harness(tmp_path)

    async def cancel(*args):
        runner.calls += 1
        raise asyncio.CancelledError

    monkeypatch.setattr(runner, "decide", cancel)
    with pytest.raises(asyncio.CancelledError):
        await runner.decide_step(state, [])
    receipt = OperationJournal(runner.sandbox, "ledger").read("ledger:model:1")
    assert runner.calls == 1
    assert receipt.output["request_count"] == 1
    assert receipt.output["request"] is None
    assert receipt.output["decision"] is None
