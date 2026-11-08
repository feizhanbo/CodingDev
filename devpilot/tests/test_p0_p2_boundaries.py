"""Behavioral regressions for resource boundaries and the public runtime port."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest

from devpilot.application.runtime import CustomRuntime
from devpilot.domain.result import AgentRunResult
from devpilot.evals.runner import EvalRunner
from devpilot.execution import execution_scope
from devpilot.processes import capture_process, run_process, run_sync
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.budget import RunBudget
from devpilot.runtime.contracts import RunOutcome, RunRequest
from devpilot.security import process_environment
from devpilot.settings import Settings
from devpilot.storage import ArtifactQuotaExceeded, CapacityReservation, tree_bytes
from devpilot.tools.context import ToolContext
from devpilot.tools.path_guard import PathGuard
from devpilot.tools.repo.read_file import ReadFile, ReadFileInput
from devpilot.workspace.sandbox import SandboxWorkspace
from tests.runtime.test_runner import _make_runner, _make_task, _resp_finish, _setup_baseline


@pytest.mark.parametrize("name", ["../outside.txt", ".env", ".git/config"])
async def test_denied_read_never_opens_content(tmp_path, monkeypatch, name):
    tool = ReadFile()
    opened = []
    real = Path.open

    def spy(path, *args, **kwargs):
        opened.append(str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", spy)
    result = await tool.execute(
        ReadFileInput(path=name), ToolContext(workspace_root=str(tmp_path), run_id="test")
    )
    assert not result.success
    assert opened == []


async def test_cached_access_reauthorizes_and_changed_content_invalidates(tmp_path, monkeypatch):
    path = tmp_path / "a.py"
    path.write_text("old", encoding="utf-8")
    stamp = path.stat()
    tool = ReadFile()
    ctx = ToolContext(workspace_root=str(tmp_path), run_id="test")
    args = ReadFileInput(path="a.py")
    first = await tool.execute(args, ctx)
    assert "old" in first.data["content"]
    path.write_text("new", encoding="utf-8")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert "new" in (await tool.execute(args, ctx)).data["content"]

    def denied(*args):
        raise PermissionError("policy revoked")

    monkeypatch.setattr(PathGuard, "validate_path", denied)

    def no_content(*args, **kwargs):
        raise AssertionError("Content read before authorization")

    monkeypatch.setattr(Path, "open", no_content)
    assert not (await tool.execute(args, ctx)).success


async def test_long_line_and_unicode_result_are_bounded(tmp_path):
    path = tmp_path / "long.py"
    with path.open("wb") as stream:
        for _ in range(1000):
            stream.write(("中文" * 1000).encode())
    ctx = ToolContext(workspace_root=str(tmp_path), run_id="test", max_output_bytes=4096)
    result = await ReadFile().execute(ReadFileInput(path="long.py"), ctx)
    assert result.success and result.data["truncated"]
    assert "truncated" in result.data["content"]
    assert len(result.model_dump_json().encode()) <= 4096


def test_process_stdin_and_independent_streams(tmp_path):
    result = capture_process(
        [
            sys.executable,
            "-c",
            "import sys;data=sys.stdin.buffer.read();sys.stdout.buffer.write(data);"
            "sys.stderr.write('error-stream')",
        ],
        cwd=tmp_path,
        stdin=b"input" * 20000,
    )
    assert result.returncode == 0
    assert result.stdout == "input" * 20000
    assert result.stderr == "error-stream"


def test_capture_timeout_and_complete_output_limit(tmp_path):
    with (
        execution_scope(deadline=time.monotonic() + 0.1, timeout_reason="tool_timeout"),
        pytest.raises(TimeoutError, match="tool_timeout"),
    ):
        capture_process([sys.executable, "-c", "import time;time.sleep(30)"], cwd=tmp_path)
    with pytest.raises(ValueError, match="complete output required"):
        capture_process(
            [sys.executable, "-c", "print('x'*100000)"], cwd=tmp_path, output_limit=1024
        )


async def test_cancelled_sync_write_is_finished_before_return(tmp_path):
    started = asyncio.Event()
    loop = asyncio.get_running_loop()

    def write():
        loop.call_soon_threadsafe(started.set)
        time.sleep(0.08)
        (tmp_path / "written").write_text("finished", encoding="utf-8")

    task = asyncio.create_task(run_sync(write))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (tmp_path / "written").read_text(encoding="utf-8") == "finished"


@pytest.mark.parametrize("backend", ["custom", "langgraph"])
async def test_preparation_budget_prevents_model_dispatch(tmp_path, monkeypatch, backend):
    if backend == "langgraph":
        from devpilot.runtime.langgraph.runner import LangGraphAgentRunner

        monkeypatch.setattr("tests.runtime.test_runner.CustomAgentRunner", LangGraphAgentRunner)
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner(
        [_resp_finish()], RuntimeConfig(preparation_timeout_seconds=0.001), base, tmp_path
    )
    result = await runner.run(_make_task())
    assert result.termination_reason == "preparation_timeout_seconds"
    assert result.budget["llm_requests"] == 0


@pytest.mark.parametrize("backend", ["custom", "langgraph"])
async def test_evaluation_budget_is_cumulative_across_rejections(tmp_path, monkeypatch, backend):
    if backend == "langgraph":
        from devpilot.runtime.langgraph.runner import LangGraphAgentRunner

        monkeypatch.setattr("tests.runtime.test_runner.CustomAgentRunner", LangGraphAgentRunner)
    from devpilot.verification.verifier import VerificationResult

    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner(
        [_resp_finish()] * 5,
        RuntimeConfig(evaluation_timeout_seconds=3, max_test_retries=10),
        base,
        tmp_path,
    )
    calls = []

    async def reject(*args):
        calls.append(1)
        await asyncio.sleep(1 if len(calls) == 1 else 30)
        return VerificationResult(success=False, checks=[], failure_reason="again")

    runner.verifier.verify = reject
    result = await runner.run(_make_task())
    assert result.termination_reason == "evaluation_timeout_seconds"
    assert len(calls) == 2
    # Windows event-loop timers may fire within one clock-resolution tick of
    # the deadline. The two invocations and termination reason above prove
    # cumulative accounting; allow scheduling granularity in wall-clock data.
    assert 2.95 <= result.budget["evaluation_seconds"] < 3.8


def test_resume_budget_includes_downtime():
    from types import SimpleNamespace

    checkpoint = SimpleNamespace(
        started_at=time.time() - 10,
        deadline_at=time.time() - 0.1,
        remaining_seconds=20,
        evaluation_seconds=5,
    )
    budget = RunBudget.start(RuntimeConfig(), checkpoint)
    with pytest.raises(TimeoutError, match="max_run_seconds"):
        budget.remaining()
    assert budget.evaluation_seconds == 5


def test_replacement_peak_and_diagnostic_reserve_are_enforced(tmp_path):
    store = SandboxWorkspace(str(tmp_path), runs_root=str(tmp_path / "runs"))
    store.artifacts_max_bytes = 4096
    store.diagnostic_reserve_bytes = 1024
    store.save_artifact("run", "checkpoint.json", "x" * 1800)
    with pytest.raises(ArtifactQuotaExceeded):
        store.save_artifact("run", "checkpoint.json", "y" * 1800)
    assert (tmp_path / "runs/run/checkpoint.json").read_text() == "x" * 1800
    store.save_artifact("run", "failure.json", '{"recoverable":false}')
    assert tree_bytes(tmp_path / "runs/run") <= 4096


def test_shared_capacity_serializes_and_reconciles_crash(tmp_path):
    package = str(Path(__file__).resolve().parents[1])
    script = (
        f"import sys;sys.path.insert(0,{package!r});"
        "import os;from pathlib import Path;from devpilot.storage import CapacityReservation;"
        "lease=CapacityReservation(Path.cwd(),Path.cwd()/'run',10000,5000,1000);"
        "lease.__enter__();(Path.cwd()/'run').mkdir();"
        "(Path.cwd()/'run/evidence').write_bytes(b'x'*100);os._exit(0)"
    )
    result = run_process(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=process_environment(),
        log=tmp_path / "process.log",
        timeout=5,
    )
    assert result.exit_code == 0
    assert (tmp_path / ".capacity-reservation.json").exists()
    with CapacityReservation(tmp_path, tmp_path / "run", 10000, 5000):
        # A different context/process cannot admit against the same shared pool.
        from devpilot.storage import RunLock

        with (
            pytest.raises(RuntimeError, match="already active"),
            RunLock(tmp_path / ".capacity.lock"),
        ):
            pass
    assert not (tmp_path / ".capacity-reservation.json").exists()
    assert (tmp_path / "run/evidence").stat().st_size == 100


async def test_evaluation_uses_only_public_runtime_port(tmp_path):
    issues = tmp_path / "issues"
    issues.mkdir()
    (issues / "DEV-001.yaml").write_text(
        "id: DEV-001\ntitle: Add\ndescription: Fix\nacceptance_criteria: []\n", encoding="utf-8"
    )
    requests = []

    class MinimalRuntime:
        __slots__ = ()

        async def execute(self, request):
            requests.append(request)
            result = AgentRunResult(
                run_id="run_01234567",
                task_id=request.task.id,
                status="completed",
                phase="completed",
                total_steps=0,
            )
            return RunOutcome(
                result,
                str(tmp_path / "ws/run_01234567/repo"),
                str(tmp_path / "runs/run_01234567"),
                evidence={"visible": {"status": "PASS", "passed": 1, "failed": 0}},
                statistics={"tokens": None, "known_tokens": 3},
            )

        async def resume(self, run_id):
            raise NotImplementedError

    settings = Settings(_env_file=None, runs_root=str(tmp_path / "runs"))
    evaluator = EvalRunner(
        str(tmp_path),
        issues_dir=str(issues),
        settings=settings,
        runner_factory=lambda **kwargs: MinimalRuntime(),
    )
    result = await evaluator.run_eval("DEV-001", fake=True)
    assert result.evaluation_status == "PASS", result.error
    assert result.token_usage is None and result.known_tokens == 3
    assert requests[0].purpose == "evaluation"
    assert requests[0].policy is not None


async def test_runtime_sessions_have_independent_budgets_cache_and_evidence(tmp_path):
    from devpilot.application.bootstrap import initialize_components

    runners = []

    def factory(**options):
        runner = initialize_components(**options)
        runners.append(runner)
        return runner

    settings = Settings(
        _env_file=None, workspace_root=str(tmp_path / "ws"), runs_root=str(tmp_path / "runs")
    )
    runtime = CustomRuntime(factory=factory, fake=True, settings=settings)
    first = await runtime.execute(RunRequest(_make_task()))
    second = await runtime.execute(RunRequest(_make_task()))
    assert first.result.status == second.result.status == "completed"
    assert first.result.budget["llm_requests"] == second.result.budget["llm_requests"] == 8
    assert first.result.run_id != second.result.run_id
    assert runners[0].session is not runners[1].session
    assert (
        runners[0].session.caches["repo.read_file"]
        is not runners[1].session.caches["repo.read_file"]
    )
    assert first.evidence["candidate"] != second.evidence["candidate"]


def test_public_testing_has_no_eval_dependency():
    import ast

    root = Path(__file__).resolve().parents[1] / "devpilot/testing"
    for file in root.glob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("devpilot.evals")


async def test_trace_failure_prevents_preparation_and_model_dispatch(tmp_path, monkeypatch):
    from devpilot.application.bootstrap import initialize_components

    settings = Settings(
        _env_file=None, workspace_root=str(tmp_path / "ws"), runs_root=str(tmp_path / "runs")
    )
    runner = initialize_components(fake=True, settings=settings)

    def fail(*args, **kwargs):
        raise OSError("synthetic trace disk failure")

    monkeypatch.setattr(runner.trace_writer, "write_event", fail)
    result = await runner.run(_make_task())
    assert result.status == "failed"
    assert result.budget["llm_requests"] == 0
    assert any("trace.jsonl" in item for item in result.artifact_errors)
    assert not Path(runner.sandbox.get_repo_path(result.run_id)).exists()


async def test_legacy_checkpoint_is_readable_but_cannot_resume(tmp_path):
    from devpilot.runtime.custom.recovery import Checkpoint
    from tests.runtime.test_recovery import interrupted_run

    base, config, run_id, path = await interrupted_run(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    assert Checkpoint.model_validate_json(path.read_text(encoding="utf-8")).schema_version == 1
    runner = _make_runner([_resp_finish()], config, base, tmp_path)
    with pytest.raises(ValueError, match="version incompatible"):
        await runner.resume(run_id)
    assert runner.agent.llm_client.call_count == 0


async def test_persistence_failure_marker_blocks_even_an_older_ready_checkpoint(tmp_path):
    from tests.runtime.test_recovery import interrupted_run

    base, config, run_id, path = await interrupted_run(tmp_path)
    (path.parent / "failure.json").write_text('{"recoverable":false}', encoding="utf-8")
    runner = _make_runner([_resp_finish()], config, base, tmp_path)
    with pytest.raises(ValueError, match="nonrecoverable"):
        await runner.resume(run_id)
    assert runner.agent.llm_client.call_count == 0


async def test_linked_workspace_root_is_denied_before_read(tmp_path, monkeypatch):
    monkeypatch.setattr("devpilot.tools.path_guard.linked", lambda path: path == tmp_path)

    def no_read(*args, **kwargs):
        raise AssertionError("Linked root content must not be opened")

    monkeypatch.setattr(Path, "open", no_read)
    result = await ReadFile().execute(
        ReadFileInput(path="a.py"), ToolContext(workspace_root=str(tmp_path), run_id="linked")
    )
    assert not result.success and "Linked workspace root" in result.error
