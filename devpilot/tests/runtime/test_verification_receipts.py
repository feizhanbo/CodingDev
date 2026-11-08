"""Verifier receipts retain evidence and cumulative evaluation charges."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.budget import RunBudget
from devpilot.runtime.langgraph.operations import ManualRecoveryRequired
from devpilot.runtime.langgraph.runner import LangGraphAgentRunner
from devpilot.verification.verifier import VerificationResult
from devpilot.workspace.sandbox import SandboxWorkspace


@pytest.fixture
def case(tmp_path):
    runner = LangGraphAgentRunner.__new__(LangGraphAgentRunner)
    runner.session = SimpleNamespace(request_count=1)
    runner.sandbox = SandboxWorkspace(str(tmp_path), str(tmp_path / "ws"), str(tmp_path / "runs"))
    directory = tmp_path / "runs" / "run"
    (directory / "trusted").mkdir(parents=True)
    workspace = tmp_path / "ws" / "run" / "repo"
    workspace.mkdir(parents=True)
    evidence = directory / "verification"
    evidence.mkdir()
    (evidence / "result.txt").write_text("passed", encoding="utf-8")
    runner.budget_service = RunBudget.start(RuntimeConfig())
    runner.registry = None
    runner.verifier = SimpleNamespace(last_results={})
    state = SimpleNamespace(run_id="run", task=DevelopmentTask(
        id="T", title="task", description="task", acceptance_criteria=[],
    ))

    async def verify(*args):
        runner.budget_service.evaluation_seconds = 4.0
        runner.verifier.last_results["run"] = {"proof": "passed"}
        return VerificationResult(success=True, checks=[], evidence_ref=str(evidence))

    runner.acceptance = SimpleNamespace(verify=AsyncMock(side_effect=verify))
    return runner, state, str(workspace), evidence


async def test_completed_verification_reuses_evidence_and_charge(case):
    runner, state, workspace, _ = case
    original_deadline = runner.budget_service.deadline_at
    first = await runner._verify_candidate(state, workspace)
    runner.budget_service.evaluation_seconds = 0
    runner.verifier.last_results.clear()
    second = await runner._verify_candidate(state, workspace)
    assert first == second
    assert runner.acceptance.verify.await_count == 1
    assert runner.budget_service.evaluation_seconds == 4
    assert runner.budget_service.deadline_at == original_deadline
    assert runner.verifier.last_results["run"] == {"proof": "passed"}
    runner.budget_service.evaluation_seconds = 8
    await runner._verify_candidate(state, workspace)
    assert runner.budget_service.evaluation_seconds == 8


async def test_changed_verification_evidence_refuses_reuse(case):
    runner, state, workspace, evidence = case
    await runner._verify_candidate(state, workspace)
    (evidence / "result.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ManualRecoveryRequired, match="evidence changed"):
        await runner._verify_candidate(state, workspace)
    assert runner.acceptance.verify.await_count == 1


async def test_interrupted_verifier_is_not_replayed(case):
    runner, state, workspace, _ = case
    runner.acceptance.verify.side_effect = TimeoutError("verification interrupted")
    with pytest.raises(TimeoutError):
        await runner._verify_candidate(state, workspace)
    with pytest.raises(ManualRecoveryRequired, match="uncertain"):
        await runner._verify_candidate(state, workspace)
    assert runner.acceptance.verify.await_count == 1
