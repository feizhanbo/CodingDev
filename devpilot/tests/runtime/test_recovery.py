"""Recover only a compatible, side-effect-free dispatch boundary."""

import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devpilot.cli import app
from devpilot.runtime.base import RuntimeConfig
from devpilot.storage import RunLock, tree_bytes
from devpilot.verification import TaskVerifier
from tests.runtime.test_runner import (
    _make_runner,
    _make_task,
    _resp_action,
    _resp_finish,
    _setup_baseline,
)


class Interrupted(BaseException):
    """Simulate abrupt interpreter loss without the runner's terminal error handler."""


async def interrupted_run(tmp_path, config=None):
    base = tmp_path / "base"
    _setup_baseline(base)
    config = config or RuntimeConfig()
    runner = _make_runner(
        [_resp_action("code.create_file", path="new.py", content="answer = 42\n")],
        config,
        base,
        tmp_path,
    )
    decide = runner.agent.decide

    async def crash(messages):
        if runner.agent.llm_client.call_count:
            raise Interrupted()
        return await decide(messages)

    runner.agent.decide = crash
    with pytest.raises(Interrupted):
        await runner.run(_make_task())
    checkpoint = next((tmp_path / "runs").glob("*/checkpoint.json"))
    return base, config, checkpoint.parent.name, checkpoint


async def test_resume_preserves_workspace_steps_budget_guard_and_unknown_usage(tmp_path):
    base, config, run_id, checkpoint = await interrupted_run(tmp_path)
    before = json.loads(checkpoint.read_text())
    assert before["stage"] == "llm_inflight"
    runner = _make_runner([_resp_finish()], config, base, tmp_path)
    result = await runner.resume(run_id)
    assert result.status == "completed"
    assert result.run_id == run_id
    assert result.total_steps == 1
    assert result.budget["llm_requests"] == 3
    assert Path(runner.sandbox.get_repo_path(run_id), "new.py").read_text() == "answer = 42\n"
    assert runner.metrics.tool_calls == 1
    assert runner.metrics.to_dict()["tokens"] is None
    assert len(runner.metrics.llm_requests) == 3
    assert runner.loop_guard._recent_tool_calls == before["guard"]["_recent_tool_calls"]
    assert json.loads(checkpoint.read_text())["stage"] == "terminal"
    with pytest.raises(ValueError, match="terminal"):
        await runner.resume(run_id)


async def test_resume_request_limit_is_not_reset(tmp_path):
    base, config, run_id, _ = await interrupted_run(tmp_path, RuntimeConfig(max_llm_requests=2))
    runner = _make_runner([_resp_finish()], config, base, tmp_path)
    result = await runner.resume(run_id)
    assert result.termination_reason == "max_llm_requests"
    assert result.budget["llm_requests"] == 2
    assert runner.agent.llm_client.call_count == 0


async def test_downtime_consumes_original_deadline(tmp_path):
    base, config, run_id, checkpoint = await interrupted_run(tmp_path)
    data = json.loads(checkpoint.read_text())
    data["deadline_at"] = time.time() - 1
    checkpoint.write_text(json.dumps(data))
    runner = _make_runner([_resp_finish()], config, base, tmp_path)
    result = await runner.resume(run_id)
    assert result.termination_reason == "max_run_seconds"
    assert runner.agent.llm_client.call_count == 0


@pytest.mark.parametrize("changed", ["workspace", "trusted", "config", "evaluation"])
async def test_resume_refuses_drift_or_evaluation(tmp_path, changed):
    base, config, run_id, checkpoint = await interrupted_run(tmp_path)
    if changed == "workspace":
        (tmp_path / "workspaces" / run_id / "repo" / "app.py").write_text("x = 9")
    elif changed == "trusted":
        (checkpoint.parent / "trusted" / "baseline" / "app.py").write_text("x = 9")
    elif changed == "config":
        config.max_steps += 1
    else:
        data = json.loads(checkpoint.read_text())
        data["purpose"] = "evaluation"
        checkpoint.write_text(json.dumps(data))
    runner = _make_runner([_resp_finish()], config, base, tmp_path)
    with pytest.raises(ValueError):
        await runner.resume(run_id)
    assert runner.agent.llm_client.call_count == 0
    assert not (checkpoint.parent / "result.json").exists()


@pytest.mark.parametrize("stage", ["tool_inflight", "verifier_inflight"])
async def test_resume_never_replays_uncertain_side_effects(tmp_path, stage):
    base, config, run_id, checkpoint = await interrupted_run(tmp_path)
    data = json.loads(checkpoint.read_text())
    data["stage"] = stage
    checkpoint.write_text(json.dumps(data))
    runner = _make_runner([_resp_finish()], config, base, tmp_path)
    with pytest.raises(ValueError, match="in-flight"):
        await runner.resume(run_id)
    assert runner.agent.llm_client.call_count == 0


async def test_interrupted_third_attempt_cannot_restart_retry_budget(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    config = RuntimeConfig()
    runner = _make_runner([], config, base, tmp_path)
    calls = []

    async def invalid(messages):
        calls.append(1)
        if len(calls) == 3:
            raise Interrupted()
        raise ValueError("invalid decision")

    runner.agent.decide = invalid
    with pytest.raises(Interrupted):
        await runner.run(_make_task())
    run_id = next((tmp_path / "runs").iterdir()).name
    resumed = _make_runner([_resp_finish()], config, base, tmp_path)
    result = await resumed.resume(run_id)
    assert result.termination_reason == "interrupted_model_retries_exhausted"
    assert result.budget["llm_requests"] == 3
    assert resumed.agent.llm_client.call_count == 0


async def test_resume_lock_refuses_another_active_runner(tmp_path):
    base, config, run_id, checkpoint = await interrupted_run(tmp_path)
    runner = _make_runner([_resp_finish()], config, base, tmp_path)
    with (
        RunLock(checkpoint.parent / ".run.lock"),
        pytest.raises(RuntimeError, match="already active"),
    ):
        await runner.resume(run_id)
    assert runner.agent.llm_client.call_count == 0


@pytest.mark.parametrize("scope", ["run", "total"])
async def test_artifact_quota_stops_admission_and_preserves_terminal_diagnostics(tmp_path, scope):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner([_resp_finish()], RuntimeConfig(), base, tmp_path)
    old = tmp_path / "runs" / "historical" / "output.log"
    old.parent.mkdir(parents=True)
    old.write_text("keep me")
    if scope == "run":
        runner.sandbox.artifacts_max_bytes = 10
    else:
        runner.sandbox.artifacts_total_max_bytes = 10
    result = await runner.run(_make_task())
    assert result.termination_reason == "artifact_quota"
    assert result.budget["llm_requests"] == 0
    assert (Path(runner.sandbox.get_runs_dir(result.run_id)) / "result.json").is_file()
    assert old.read_text() == "keep me"


def test_capacity_counts_git_logs_and_unfiltered_physical_files(tmp_path):
    for name in (".git/object", "tests/a.log", "example.db"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"abc")
    assert tree_bytes(tmp_path) == 9


def test_cli_resume_rejects_invalid_id_without_model_request(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVPILOT_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path))
    outcome = CliRunner().invoke(app, ["resume", "../outside", "--env-file", "absent"])
    assert outcome.exit_code == 1
    assert "Invalid run ID" in outcome.stdout


@pytest.mark.parametrize("phase", ["tool", "verifier"])
async def test_deadline_cancels_async_tool_and_verifier(tmp_path, phase):
    import asyncio

    base = tmp_path / "base"
    _setup_baseline(base)
    config = RuntimeConfig(max_run_seconds=1.0)
    response = _resp_action("git.status") if phase == "tool" else _resp_finish()
    runner = _make_runner([response], config, base, tmp_path)
    cancelled = []

    async def slow(*args):
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.append(True)

    if phase == "tool":
        runner.registry.execute = slow
    else:
        runner.verifier = TaskVerifier(config)
        runner.verifier.verify = slow
    result = await asyncio.wait_for(runner.run(_make_task()), 5)
    assert result.status == "failed"
    assert result.termination_reason in {"run_timeout", "max_run_seconds"}
    assert cancelled == [True]


@pytest.mark.parametrize("name", ["llm_timeout_seconds", "max_run_seconds"])
@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_nonfinite_deadlines_cannot_disable_budgets(name, value):
    with pytest.raises(ValueError):
        RuntimeConfig(**{name: value})


async def test_actual_interrupted_tool_has_nonreplayable_checkpoint(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    config = RuntimeConfig()
    runner = _make_runner(
        [_resp_action("code.create_file", path="partial.py", content="x=1")], config, base, tmp_path
    )

    async def incomplete(action, ctx):
        Path(ctx.workspace_root, "partial.py").write_text("partial effect")
        raise Interrupted()

    runner.registry.execute = incomplete
    with pytest.raises(Interrupted):
        await runner.run(_make_task())
    checkpoint = next((tmp_path / "runs").glob("*/checkpoint.json"))
    assert json.loads(checkpoint.read_text())["stage"] == "tool_inflight"
    resumed = _make_runner([_resp_finish()], config, base, tmp_path)
    with pytest.raises(ValueError, match="in-flight"):
        await resumed.resume(checkpoint.parent.name)


async def test_progress_failure_does_not_lose_terminal_result(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner([_resp_finish()], RuntimeConfig(), base, tmp_path)

    def broken_display(*args):
        raise ValueError("synthetic display error")

    runner.on_event = broken_display
    result = await runner.run(_make_task())
    assert result.status == "completed"
    assert Path(runner.sandbox.get_runs_dir(result.run_id), "result.json").is_file()


async def test_ready_boundary_restores_test_retry_and_repair_history(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    config = RuntimeConfig(max_test_retries=2)
    runner = _make_runner([_resp_action("test_run", target="missing.py")], config, base, tmp_path)
    save = runner._checkpoint

    def stop_after_first_tool(state, stage="ready"):
        save(state, stage)
        if stage == "ready" and state.total_steps == 1:
            raise Interrupted()

    runner._checkpoint = stop_after_first_tool
    with pytest.raises(Interrupted):
        await runner.run(_make_task())
    checkpoint = next((tmp_path / "runs").glob("*/checkpoint.json"))
    saved = json.loads(checkpoint.read_text())
    assert saved["stage"] == "ready"
    assert saved["state"]["retry_count"] == 1
    assert saved["state"]["repair_required"]
    resumed = _make_runner(
        [_resp_action("test.run", target="missing-again.py")], config, base, tmp_path
    )
    result = await resumed.resume(checkpoint.parent.name)
    assert result.status == "failed"
    assert result.error == "Max retries exceeded"
    assert result.budget["llm_requests"] == 2
    assert resumed.metrics.test_retries == 2
