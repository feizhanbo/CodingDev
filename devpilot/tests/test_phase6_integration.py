"""Full integration test for Phase 6: Trace + Verifier + Self-correction."""

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
    _write(base / "test_app.py", "def test_app():\n    assert False\n")


def _setup_baseline_passing(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\n")
    _write(base / "test_pass.py", "def test_pass():\n    assert True\n")


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
    verifier = TaskVerifier(config)
    trace_writer = TraceWriter(str(tmp_path / "runs"))
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

PATCH_FIX_TEST = (
    "--- a/test_app.py\n"
    "+++ b/test_app.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def test_app():\n"
    "-    assert False\n"
    "+    assert True\n"
)


class TestPhase6FullIntegration:
    """Full integration: Trace + Verifier + Self-correction."""

    async def test_self_correction_with_trace_and_metrics(
        self, tmp_path: Path
    ) -> None:
        """Agent fails verifier, repairs, passes verifier.

        Verifies:
        - trace.jsonl contains all expected event types
        - result.json contains metrics
        - state.json is saved with correct final phase
        - self-correction loop works end-to-end
        """
        baseline = tmp_path / "baseline"
        _setup_baseline_failing(baseline)

        responses = [
            _resp_action("repo.search_code", query="test"),
            _resp_action("repo.read_file", path="test_app.py"),
            _resp_action("code.apply_patch", patch=PATCH_MODIFY_APP),
            _resp_action("test.run", target="test_app.py"),
            _resp_finish(summary="done", risk="low"),
            _resp_action("code.apply_patch", patch=PATCH_FIX_TEST),
            _resp_action("test.run", target="test_app.py"),
            _resp_finish(summary="all done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        # --- Result assertions ---
        assert result.status == "completed"
        assert result.phase == "completed"
        assert result.error is None

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id

        # --- trace.jsonl assertions ---
        trace_path = runs_dir / "trace.jsonl"
        assert trace_path.is_file()

        trace_lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
        trace_events = [json.loads(line) for line in trace_lines]
        event_types = [e["event"] for e in trace_events]

        assert "run_started" in event_types
        assert "agent_decision" in event_types
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert "verifier_started" in event_types
        assert "verifier_result" in event_types
        assert "state_transition" in event_types
        assert "run_completed" in event_types

        # Every trace event must have a timestamp
        for evt in trace_events:
            assert evt["timestamp"]
            assert len(evt["timestamp"]) > 0

        # --- result.json assertions ---
        result_path = runs_dir / "result.json"
        assert result_path.is_file()
        result_data = json.loads(
            result_path.read_text(encoding="utf-8")
        )
        assert result_data["status"] == "completed"
        assert "metrics" in result_data
        metrics = result_data["metrics"]
        assert "tool_calls" in metrics
        assert "duration_ms" in metrics
        assert "finish_rejected_count" in metrics
        assert metrics["finish_rejected_count"] >= 1
        assert metrics["tool_calls"] >= 3

        # --- state.json assertions ---
        state_path = runs_dir / "state.json"
        assert state_path.is_file()
        state_data = json.loads(
            state_path.read_text(encoding="utf-8")
        )
        assert state_data["phase"] == "completed"
        assert state_data["run_id"] == result.run_id
        assert len(state_data["modified_files"]) > 0

        # --- Self-correction assertions ---
        verifier_obs = [
            o for o in result.observations if o.source == "verifier"
        ]
        assert len(verifier_obs) >= 1
        assert runner.metrics.finish_rejected_count == 1
        assert runner.metrics.test_retries == 1

    async def test_verifier_rejects_empty_diff_then_accepted(
        self, tmp_path: Path
    ) -> None:
        """Agent requests finish with no changes; verifier rejects."""
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

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        trace_path = runs_dir / "trace.jsonl"
        trace_events = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").strip().split("\n")
        ]
        event_types = [e["event"] for e in trace_events]

        # Should have verifier_started and verifier_result
        assert "verifier_started" in event_types
        assert "verifier_result" in event_types

        # First verifier_result should be failure
        verifier_results = [
            e for e in trace_events if e["event"] == "verifier_result"
        ]
        assert len(verifier_results) >= 2
        first_result_data = verifier_results[0].get("data", {})
        assert first_result_data.get("success") is False

    async def test_max_verifier_retries_leads_to_failure(
        self, tmp_path: Path
    ) -> None:
        """Agent keeps requesting finish without making changes.

        Verifier rejects each time until max_test_retries is exceeded.
        """
        baseline = tmp_path / "baseline"
        _setup_baseline_passing(baseline)

        responses = [
            _resp_finish(summary="done", risk="low"),
            _resp_finish(summary="done", risk="low"),
            _resp_finish(summary="done", risk="low"),
            _resp_finish(summary="done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "failed"
        assert "retries" in (result.error or "").lower()
        assert runner.metrics.finish_rejected_count == 3

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        trace_path = runs_dir / "trace.jsonl"
        trace_events = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").strip().split("\n")
        ]
        event_types = [e["event"] for e in trace_events]

        assert "verifier_started" in event_types
        assert "verifier_result" in event_types
        assert "run_failed" in event_types

    async def test_guardrail_violation_emits_trace(
        self, tmp_path: Path
    ) -> None:
        """Guardrail violation (duplicate action) emits guardrail_triggered."""
        baseline = tmp_path / "baseline"
        _setup_baseline_passing(baseline)

        same = _resp_action("repo.search_code", query="same")
        responses = [same, same, same, same]
        config = RuntimeConfig(max_steps=30)
        runner = _make_runner(responses, config, baseline, tmp_path)

        result = await runner.run(_make_task())

        assert result.status == "failed"

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        trace_path = runs_dir / "trace.jsonl"
        trace_events = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").strip().split("\n")
        ]
        event_types = [e["event"] for e in trace_events]

        assert "guardrail_triggered" in event_types
        assert "run_failed" in event_types

    async def test_no_verifier_backward_compat(self, tmp_path: Path) -> None:
        """Without verifier, agent completes immediately on finish."""
        baseline = tmp_path / "baseline"
        _setup_baseline_passing(baseline)

        responses = [
            _resp_action("repo.search_code", query="x"),
            _resp_finish(summary="done", risk="low"),
        ]
        config = RuntimeConfig(max_steps=30)
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
        trace_writer = TraceWriter(str(tmp_path / "runs"))
        metrics = MetricsCollector()
        runner = CustomAgentRunner(
            agent=agent,
            registry=registry,
            sandbox=sandbox,
            state_manager=state_manager,
            context_builder=context_builder,
            loop_guard=loop_guard,
            config=config,
            verifier=None,
            trace_writer=trace_writer,
            metrics=metrics,
        )

        result = await runner.run(_make_task())

        assert result.status == "completed"
        assert result.total_steps == 1

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        trace_path = runs_dir / "trace.jsonl"
        trace_events = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").strip().split("\n")
        ]
        event_types = [e["event"] for e in trace_events]

        assert "run_started" in event_types
        assert "run_completed" in event_types
        # No verifier events without verifier
        assert "verifier_started" not in event_types
