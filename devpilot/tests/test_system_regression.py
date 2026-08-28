"""System-level regression tests for DevPilot V1.

These tests verify the full system works end-to-end:
issue -> workspace -> agent -> tools -> verifier -> result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devpilot.cli import initialize_components, load_issue
from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
from devpilot.llm.base import LLMResponse
from devpilot.llm.fake import FakeLLMClient
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.context import ToolContext

_ISSUE_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "issues"
    / "DEV-001.yaml"
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _setup_baseline(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\nz = 3\n")
    _write(base / "test_pass.py", "def test_ok():\n    assert True\n")


_PATCH = (
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1,2 +1,3 @@\n"
    " x = 1\n"
    "+y = 2\n"
    " z = 3\n"
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


def _make_responses() -> list[LLMResponse]:
    """Build a response sequence that exercises all major phases."""
    return [
        _resp_action("repo.search_code", query="orders"),
        _resp_action("repo.read_file", path="app.py"),
        _resp_action("code.apply_patch", patch=_PATCH),
        _resp_action("test.run"),
        _resp_finish(summary="Added status filter", risk="low"),
    ]


class TestSystemRegression:
    """System-level regression tests for DevPilot V1."""

    async def test_full_e2e_with_fake_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test complete E2E flow: issue -> workspace -> agent -> tools -> verifier -> result."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        config = RuntimeConfig(max_steps=30)
        runner = initialize_components(
            config, fake=True, base_repo=str(baseline)
        )
        runner.agent.llm_client = FakeLLMClient(_make_responses())

        task = load_issue(str(_ISSUE_PATH))
        result = await runner.run(task)

        # Verify result status
        assert result.status == "completed"
        assert result.phase == "completed"
        assert result.error is None
        assert result.summary == "Added status filter"
        assert result.risk == "low"
        assert len(result.modified_files) > 0
        assert "app.py" in result.modified_files

        # Verify all artifacts created
        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        assert (runs_dir / "state.json").is_file()
        assert (runs_dir / "result.json").is_file()
        assert (runs_dir / "trace.jsonl").is_file()

        # Verify state.json content
        state_data = json.loads(
            (runs_dir / "state.json").read_text(encoding="utf-8")
        )
        assert state_data["phase"] == "completed"
        assert state_data["run_id"] == result.run_id

        # Verify result.json content
        result_data = json.loads(
            (runs_dir / "result.json").read_text(encoding="utf-8")
        )
        assert result_data["status"] == "completed"
        assert "metrics" in result_data

        # Verify trace contains all expected event types
        trace_events = [
            json.loads(line)
            for line in (runs_dir / "trace.jsonl")
            .read_text(encoding="utf-8")
            .strip()
            .split("\n")
        ]
        event_types = [e["event"] for e in trace_events]
        assert "run_started" in event_types
        assert "agent_decision" in event_types
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert "verifier_started" in event_types
        assert "verifier_result" in event_types
        assert "run_completed" in event_types

    async def test_workspace_isolation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify workspace isolation: each run gets clean workspace."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        config = RuntimeConfig(max_steps=30)

        # Run 1
        runner1 = initialize_components(
            config, fake=True, base_repo=str(baseline)
        )
        runner1.agent.llm_client = FakeLLMClient(_make_responses())
        task = load_issue(str(_ISSUE_PATH))
        result1 = await runner1.run(task)
        assert result1.status == "completed"

        workspace1 = Path(runner1.sandbox.get_repo_path(result1.run_id))
        # Verify workspace1 has the modification
        assert (workspace1 / "app.py").is_file()
        app1_content = (workspace1 / "app.py").read_text(encoding="utf-8")
        assert "y = 2" in app1_content

        # Run 2 - should get a clean workspace
        runner2 = initialize_components(
            config, fake=True, base_repo=str(baseline)
        )
        runner2.agent.llm_client = FakeLLMClient(_make_responses())
        result2 = await runner2.run(task)
        assert result2.status == "completed"

        workspace2 = Path(runner2.sandbox.get_repo_path(result2.run_id))
        # Verify workspaces are in separate directories
        assert workspace1 != workspace2
        assert result1.run_id != result2.run_id

        # Verify workspace2 also has the modification (from its own run)
        app2_content = (workspace2 / "app.py").read_text(encoding="utf-8")
        assert "y = 2" in app2_content

        # Verify workspace1 was not affected by run 2
        app1_after = (workspace1 / "app.py").read_text(encoding="utf-8")
        assert app1_after == app1_content

    async def test_trace_completeness(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify trace.jsonl contains all expected events with required fields."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        config = RuntimeConfig(max_steps=30)
        runner = initialize_components(
            config, fake=True, base_repo=str(baseline)
        )
        runner.agent.llm_client = FakeLLMClient(_make_responses())

        task = load_issue(str(_ISSUE_PATH))
        result = await runner.run(task)

        assert result.status == "completed"

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        trace_path = runs_dir / "trace.jsonl"
        assert trace_path.is_file()

        trace_events = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").strip().split("\n")
        ]

        # Each event must have run_id, step, phase, timestamp
        for evt in trace_events:
            assert "run_id" in evt
            assert evt["run_id"] == result.run_id
            assert "step" in evt
            assert isinstance(evt["step"], int)
            assert "phase" in evt
            assert len(evt["phase"]) > 0
            assert "timestamp" in evt
            assert len(evt["timestamp"]) > 0
            assert "event" in evt

        # Verify all expected event types are present
        event_types = [e["event"] for e in trace_events]
        expected_events = [
            "run_started",
            "agent_decision",
            "tool_call",
            "tool_result",
            "verifier_started",
            "verifier_result",
            "run_completed",
        ]
        for expected in expected_events:
            assert expected in event_types, f"Missing event: {expected}"

    async def test_hidden_tests_isolation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify hidden tests cannot be accessed by agent during run."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        # Create hidden tests outside the workspace
        hidden_tests_dir = tmp_path / "hidden_tests" / "DEV-001"
        _write(
            hidden_tests_dir / "test_hidden.py",
            "def test_secret():\n    assert True\n",
        )

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        config = RuntimeConfig(max_steps=30)
        runner = initialize_components(
            config, fake=True, base_repo=str(baseline)
        )
        runner.agent.llm_client = FakeLLMClient(_make_responses())

        task = load_issue(str(_ISSUE_PATH))
        result = await runner.run(task)
        assert result.status == "completed"

        workspace_path = runner.sandbox.get_repo_path(result.run_id)

        # Verify hidden_tests is NOT in the workspace during the run
        workspace_hidden = Path(workspace_path) / "hidden_tests"
        assert not workspace_hidden.exists()

        # Verify hidden tests directory is outside workspace root
        hidden_resolved = hidden_tests_dir.resolve()
        workspace_root = Path(tmp_path / "workspaces").resolve()
        assert not str(hidden_resolved).startswith(str(workspace_root))

        # Verify agent tools reject paths outside workspace
        registry = runner.registry
        read_tool = registry.get("repo.read_file")
        assert read_tool is not None
        ctx = ToolContext(workspace_root=workspace_path, run_id=result.run_id)

        action = ToolAction(
            tool="repo.read_file",
            arguments={"path": str(hidden_tests_dir / "test_hidden.py")},
        )
        tool_result = await registry.execute(action, ctx)
        assert not tool_result.success

    async def test_policy_consistency(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify max_steps, max_retries, forbidden_files policies are enforced."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        # Test max_steps enforcement
        config = RuntimeConfig(max_steps=2, max_test_retries=3)
        runner = initialize_components(
            config, fake=True, base_repo=str(baseline)
        )
        # Agent keeps searching, never finishes - will exceed max_steps
        responses = [
            _resp_action("repo.search_code", query="a"),
            _resp_action("repo.search_code", query="b"),
            _resp_action("repo.search_code", query="c"),
        ]
        runner.agent.llm_client = FakeLLMClient(responses)

        task = load_issue(str(_ISSUE_PATH))
        result = await runner.run(task)
        assert result.status == "failed"
        assert "max_steps" in (result.error or "").lower()

        # Test max_retries enforcement
        config2 = RuntimeConfig(max_steps=30, max_test_retries=1)
        runner2 = initialize_components(
            config2, fake=True, base_repo=str(baseline)
        )
        # Agent requests finish without changes, verifier rejects
        responses2 = [
            _resp_finish(summary="done", risk="low"),
            _resp_finish(summary="done", risk="low"),
        ]
        runner2.agent.llm_client = FakeLLMClient(responses2)

        result2 = await runner2.run(task)
        assert result2.status == "failed"
        assert "retries" in (result2.error or "").lower()

        # Test forbidden files rejection via PathGuard
        from devpilot.tools.path_guard import PathGuard

        guard = PathGuard(str(tmp_path / "workspaces"))
        with pytest.raises(PermissionError):
            guard.validate_path(".env")
        with pytest.raises(PermissionError):
            guard.validate_path("../secret.env")
