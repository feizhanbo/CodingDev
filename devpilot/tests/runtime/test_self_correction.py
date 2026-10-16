"""Tests for the self-correction repair loop in CustomAgentRunner."""

from __future__ import annotations

import json
from pathlib import Path

from devpilot.agents.developer import DeveloperAgent
from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
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


def _full_registry() -> ToolRegistry:
    reg = ToolRegistry()
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
        reg.register(tool)
    return reg


def _make_task() -> DevelopmentTask:
    return DevelopmentTask(
        id="DEV-001",
        title="Fix the bug",
        description="Fix failing tests",
        acceptance_criteria=["Tests pass"],
    )


def _setup_baseline_failing(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\n")
    _write(base / "test_app.py", "from app import x\n\ndef test_app():\n    assert x == 2\n")


def _setup_baseline_passing(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\n")
    _write(base / "test_pass.py", "def test_pass():\n    assert True\n")


def _make_runner(
    responses: list[LLMResponse],
    config: RuntimeConfig,
    baseline: Path,
    tmp_path: Path,
    use_verifier: bool = True,
    use_trace: bool = True,
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
    verifier = TaskVerifier(config) if use_verifier else None
    trace_writer = (
        TraceWriter(str(tmp_path / "runs")) if use_trace else None
    )
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


PATCH_MODIFY_APP = (
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1 +1,2 @@\n"
    "-x = 1\n"
    "+x = 1\n"
    "+y = 2\n"
)

PATCH_FIX_APP = (
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1,2 +1,2 @@\n"
    "-x = 1\n"
    "+x = 2\n"
    " y = 2\n"
)


class TestRepairLoopComplete:
    async def test_tests_fail_repair_pass_verifier_complete(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline_failing(baseline)

        responses = [
            _resp_action("repo.search_code", query="test"),
            _resp_action("repo.read_file", path="test_app.py"),
            _resp_action("code.apply_patch", patch=PATCH_MODIFY_APP),
            _resp_action("test.run", target="test_app.py"),
            _resp_finish(summary="done", risk="low"),
            _resp_action("code.apply_patch", patch=PATCH_FIX_APP),
            _resp_action("test.run", target="test_app.py"),
            _resp_finish(summary="all done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"
        assert runner.metrics.test_retries == 1
        verifier_rejections = [
            o for o in result.observations if o.source == "verifier"
        ]
        assert len(verifier_rejections) >= 1


class TestMaxRetriesExceeded:
    async def test_tests_fail_thrice_max_retries_failed(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline_failing(baseline)

        responses = [
            _resp_action("repo.search_code", query="test"),
            _resp_action("test.run", target="test_app.py"),
            _resp_action("test.run", target="test_app.py"),
            _resp_action("test.run", target="test_app.py"),
        ]
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "failed"
        assert "max retries" in (result.error or "").lower()
        assert runner.metrics.test_retries == 3


class TestVerifierRejectsEmptyDiff:
    async def test_finish_rejected_then_patch_then_accepted(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline_passing(baseline)

        responses = [
            _resp_finish(summary="done", risk="low"),
            _resp_action("code.apply_patch", patch=PATCH_MODIFY_APP),
            _resp_finish(summary="all done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"
        assert runner.metrics.finish_rejected_count == 1


class TestTraceEventsRecorded:
    async def test_trace_jsonl_contains_expected_events(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline_passing(baseline)

        responses = [
            _resp_finish(summary="done", risk="low"),
            _resp_action("code.apply_patch", patch=PATCH_MODIFY_APP),
            _resp_finish(summary="all done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"

        trace_path = (
            Path(runner.sandbox.runs_root) / result.run_id / "trace.jsonl"
        )
        assert trace_path.is_file()

        lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
        events = [json.loads(line)["event"] for line in lines]

        assert "run_started" in events
        assert "agent_decision" in events
        assert "verifier_started" in events
        assert "verifier_result" in events
        assert "run_completed" in events

    async def test_result_json_contains_metrics(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline_passing(baseline)

        responses = [
            _resp_finish(summary="done", risk="low"),
            _resp_action("code.apply_patch", patch=PATCH_MODIFY_APP),
            _resp_finish(summary="all done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        result_path = (
            Path(runner.sandbox.runs_root) / result.run_id / "result.json"
        )
        result_data = json.loads(
            result_path.read_text(encoding="utf-8")
        )
        assert "metrics" in result_data
        assert "tool_calls" in result_data["metrics"]
        assert "duration_ms" in result_data["metrics"]
        assert "finish_rejected_count" in result_data["metrics"]


class TestBackwardCompatNoVerifier:
    async def test_no_verifier_completes_immediately(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline_passing(baseline)

        responses = [
            _resp_action("repo.search_code", query="x"),
            _resp_finish(summary="done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(
            responses, config, baseline, tmp_path,
            use_verifier=False, use_trace=False,
        )

        result = await runner.run(_make_task())

        assert result.status == "completed"
        assert result.total_steps == 1
