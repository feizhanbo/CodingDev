"""Tests for CustomAgentRunner."""

from __future__ import annotations

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
from devpilot.workspace.sandbox import SandboxWorkspace


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _setup_baseline(base: Path) -> None:
    """Create a baseline repo with source files and a passing test."""
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\n")
    _write(base / "test_pass.py", "def test_ok():\n    assert True\n")


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
        title="Add order creation endpoint",
        description="Create a POST /orders endpoint",
        acceptance_criteria=["Returns 201 on success", "Validates input"],
        constraints=["Do not change response schema"],
    )


def _make_runner(
    responses: list[LLMResponse],
    config: RuntimeConfig,
    baseline: Path,
    tmp_path: Path,
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
    return CustomAgentRunner(
        agent=agent,
        registry=registry,
        sandbox=sandbox,
        state_manager=state_manager,
        context_builder=context_builder,
        loop_guard=loop_guard,
        config=config,
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


class TestRunnerFullFlow:
    async def test_full_loop_completes(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [
            _resp_action("repo.search_code", query="orders"),
            _resp_action("repo.read_file", path="app.py"),
            _resp_action("code.create_file", path="new.py", content="z = 3\n"),
            _resp_action("test.run", target="test_pass.py"),
            _resp_finish(summary="All done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"
        assert result.phase == "completed"
        assert result.total_steps == 4
        assert result.summary == "All done"
        assert result.risk == "low"
        assert result.error is None
        assert result.duration_ms is not None

    async def test_state_transitions_through_phases(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [
            _resp_action("repo.search_code", query="orders"),
            _resp_action("repo.read_file", path="app.py"),
            _resp_finish(),
        ]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"
        assert result.phase == "completed"
        assert result.total_steps == 2

    async def test_artifacts_saved(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [
            _resp_action("repo.search_code", query="x"),
            _resp_finish(summary="done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        assert (runs_dir / "state.json").is_file()
        assert (runs_dir / "result.json").is_file()

        state_text = (runs_dir / "state.json").read_text(encoding="utf-8")
        assert result.run_id in state_text

        result_text = (runs_dir / "result.json").read_text(encoding="utf-8")
        assert "completed" in result_text


class TestRunnerFinishEarly:
    async def test_finish_immediately(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [_resp_finish(summary="nothing to do", risk="low")]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"
        assert result.total_steps == 0
        assert result.summary == "nothing to do"

    async def test_finish_after_one_tool(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [
            _resp_action("repo.list_files", path="."),
            _resp_finish(summary="done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "completed"
        assert result.total_steps == 1


class TestRunnerMaxSteps:
    async def test_max_steps_exceeded(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        responses = [
            _resp_action("repo.search_code", query="a"),
            _resp_action("repo.search_code", query="b"),
        ]
        config = RuntimeConfig(max_steps=2)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "failed"
        assert result.phase == "failed"
        assert "max_steps" in (result.error or "").lower() or "max steps" in (
            result.error or ""
        ).lower()
        assert result.total_steps == 2


class TestRunnerGuardrailViolations:
    async def test_duplicate_action_detected(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        same = _resp_action("repo.search_code", query="same")
        responses = [same, same, same, same]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "failed"
        assert "Repeated" in (result.error or "")

    async def test_guardrail_violation_saves_artifacts(
        self, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        same = _resp_action("repo.search_code", query="x")
        responses = [same, same, same, same]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "failed"
        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        assert (runs_dir / "state.json").is_file()
        assert (runs_dir / "result.json").is_file()
