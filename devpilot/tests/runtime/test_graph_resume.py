"""Restart graph execution with fresh services across durable receipt boundaries."""

import asyncio
import json
import sys

import pytest

from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.langgraph.operations import ManualRecoveryRequired, OperationJournal
from devpilot.runtime.langgraph.runner import LangGraphAgentRunner
from devpilot.tracing import TraceWriter
from devpilot.verification.verifier import VerificationResult
from tests.runtime import test_runner as helpers


class Interrupted(BaseException):
    pass


@pytest.fixture
def make_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "CustomAgentRunner", LangGraphAgentRunner)
    baseline = tmp_path / "baseline"
    helpers._setup_baseline(baseline)

    def make(responses):
        return helpers._make_runner(responses, RuntimeConfig(), baseline, tmp_path)

    return make


def run_id(runner):
    return next(path.name for path in runner.sandbox.runs_root.glob("run_*") if path.is_dir())


async def test_resume_reuses_model_decision_after_receipt(make_runner, monkeypatch):
    runner = make_runner([helpers._resp_finish()])
    original = runner._end_model_request

    def crash(state, decision):
        original(state, decision)
        raise Interrupted()

    monkeypatch.setattr(runner, "_end_model_request", crash)
    with pytest.raises(Interrupted):
        await runner.run(helpers._make_task())
    restarted = make_runner([])
    result = await restarted.resume(run_id(runner))
    assert result.status == "completed"
    assert restarted.agent.llm_client.call_count == 0
    assert result.budget["llm_requests"] == 1


async def test_dependency_drift_refuses_real_resume_before_dispatch(make_runner, monkeypatch):
    runner = make_runner([helpers._resp_finish()])
    original = runner._end_model_request

    def crash(state, decision):
        original(state, decision)
        raise Interrupted()

    monkeypatch.setattr(runner, "_end_model_request", crash)
    with pytest.raises(Interrupted):
        await runner.run(helpers._make_task())
    identifier = run_id(runner)
    directory = runner.sandbox.runs_root / identifier
    manifest_path = directory / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "langgraph" in manifest["dependencies"]
    manifest["dependencies"]["langgraph"] = "0.0.0-incompatible"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    before = {path.relative_to(directory): path.read_bytes()
              for path in directory.rglob("*") if path.is_file()}

    restarted = make_runner([])
    with pytest.raises(ValueError, match="dependency versions changed"):
        await restarted.resume(identifier)
    assert restarted.agent.llm_client.call_count == 0
    assert {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()} == before


async def test_model_receipt_resumes_in_new_process(make_runner, monkeypatch, tmp_path):
    runner = make_runner([helpers._resp_finish()])
    original = runner._end_model_request

    def crash(state, decision):
        original(state, decision)
        raise Interrupted()

    monkeypatch.setattr(runner, "_end_model_request", crash)
    with pytest.raises(Interrupted):
        await runner.run(helpers._make_task())
    script = """
import asyncio, json, sys
from pathlib import Path
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.langgraph.runner import LangGraphAgentRunner
from tests.runtime import test_runner as helpers
helpers.CustomAgentRunner = LangGraphAgentRunner
root = Path(sys.argv[1])
runner = helpers._make_runner([], RuntimeConfig(), root / 'baseline', root)
result = asyncio.run(runner.resume(sys.argv[2]))
print(json.dumps({'status': result.status, 'calls': runner.agent.llm_client.call_count,
                  'requests': result.budget['llm_requests']}))
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script, str(tmp_path), run_id(runner),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=90)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    assert process.returncode == 0, stderr.decode(errors="replace")
    assert json.loads(stdout.decode().splitlines()[-1]) == {
        "status": "completed", "calls": 0, "requests": 1,
    }
@pytest.mark.parametrize("record_completion", [True, False])
async def test_resume_tool_crash_window(make_runner, monkeypatch, record_completion):
    runner = make_runner([helpers._resp_action("code.create_file", path="new.py", content="x=1\n")])
    original = OperationJournal.complete

    def crash(journal, operation_id, after, output):
        if operation_id.endswith(":tool"):
            if record_completion:
                original(journal, operation_id, after, output)
            raise Interrupted()
        return original(journal, operation_id, after, output)

    with monkeypatch.context() as patch:
        patch.setattr(OperationJournal, "complete", crash)
        with pytest.raises(Interrupted):
            await runner.run(helpers._make_task())
    restarted = make_runner([helpers._resp_finish()])
    if not record_completion:
        with pytest.raises(ManualRecoveryRequired, match="uncertain"):
            await restarted.resume(run_id(runner))
        assert restarted.agent.llm_client.call_count == 0
        return
    result = await restarted.resume(run_id(runner))
    assert result.status == "completed"
    assert restarted.metrics.tool_calls == 1
    assert result.total_steps == 1
    assert result.budget["llm_requests"] == 2


async def test_resume_completed_graph_preserves_evidence(make_runner, monkeypatch):
    runner = make_runner([helpers._resp_finish()])

    async def verify(task, workspace, state, registry):
        runner.verifier.last_results[state.run_id] = {"proof": "saved"}
        return VerificationResult(success=True, checks=[])

    def crash(*args):
        raise Interrupted()

    monkeypatch.setattr(runner.verifier, "verify", verify)
    monkeypatch.setattr(runner, "_publish_terminal", crash)
    with pytest.raises(Interrupted):
        await runner.run(helpers._make_task())
    restarted = make_runner([])

    async def unexpected(*args):
        raise AssertionError("Completed verification must not be repeated")

    monkeypatch.setattr(restarted.verifier, "verify", unexpected)
    outcome = await restarted.resume_outcome(run_id(runner))
    assert outcome.result.status == "completed"
    assert outcome.evidence == {"proof": "saved"}
    assert restarted.agent.llm_client.call_count == 0


async def test_replayed_observation_does_not_duplicate_trace(make_runner, monkeypatch):
    runner = make_runner([helpers._resp_action("code.create_file", path="new.py", content="x=1\n")])

    def tracing(instance):
        instance.trace_writer = TraceWriter(str(instance.sandbox.runs_root))
        instance.trace_writer.artifact_store = instance.sandbox

    tracing(runner)
    original = runner.observe_step

    def crash(*args):
        original(*args)
        raise Interrupted()

    monkeypatch.setattr(runner, "observe_step", crash)
    with pytest.raises(Interrupted):
        await runner.run(helpers._make_task())
    restarted = make_runner([helpers._resp_finish()])
    tracing(restarted)
    identifier = run_id(runner)
    result = await restarted.resume(identifier)
    assert result.status == "completed"
    lines = (runner.sandbox.runs_root / identifier / "trace.jsonl").read_text().splitlines()
    events = [json.loads(line) for line in lines]
    assert sum(event["event"] == "tool_result" for event in events) == 1
    assert sum(event["event"] == "run_started" for event in events) == 1
    assert sum(event["event"] == "run_completed" for event in events) == 1
    identities = [event["event_id"] for event in events]
    assert all(identities)
    assert len(identities) == len(set(identities))
