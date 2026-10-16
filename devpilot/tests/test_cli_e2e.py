"""End-to-end tests for the CLI and agent runner with FakeLLMClient."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from devpilot.cli import (
    app,
    initialize_components,
    load_issue,
    register_all_tools,
)
from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
from devpilot.llm.base import LLMResponse
from devpilot.llm.fake import FakeLLMClient
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.registry import ToolRegistry

_ISSUE_PATH = (
    Path(__file__).resolve().parent.parent
    / "devpilot" / "evals"
    / "issues"
    / "DEV-001.yaml"
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _setup_baseline(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\nz = 3\n")
    _write(
        base / "test_pass.py",
        "from app import x, z\n\ndef test_ok():\n    assert (x, z) == (1, 3)\n",
    )


_PATCH = (
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1,2 +1,3 @@\n"
    " x = 1\n"
    "+y = 2\n"
    " z = 3\n"
)


def _make_responses() -> list[LLMResponse]:
    return [
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="repo.search_code",
                    arguments={"query": "orders"},
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="repo.read_file", arguments={"path": "app.py"}
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="code.apply_patch", arguments={"patch": _PATCH}
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="code.create_file",
                    arguments={
                        "path": "tests/test_added_value.py",
                        "content": (
                            "from app import y\n\ndef test_added_value():\n"
                            "    assert y == 2\n"
                        ),
                    },
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(tool="test.run", arguments={})
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                finish=FinishIntent(
                    summary="Added status filter", risk="low"
                )
            ),
            model="fake",
        ),
    ]


class TestDev001E2E:
    async def test_dev001_e2e_with_fake_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test DEV-001 end-to-end with FakeLLMClient."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        config = RuntimeConfig(max_steps=30)
        events: list[tuple[str, dict]] = []

        def callback(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        runner = initialize_components(
            config,
            fake=True,
            base_repo=str(baseline),
            on_event=callback,
        )
        runner.agent.llm_client = FakeLLMClient(_make_responses())

        task = load_issue(str(_ISSUE_PATH))
        result = await runner.run(task)

        assert result.status == "completed"
        assert result.phase == "completed"
        assert result.total_steps == 5
        assert result.summary == "Added status filter"
        assert result.risk == "low"
        assert result.error is None
        assert len(result.modified_files) > 0
        assert "app.py" in result.modified_files

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        assert (runs_dir / "state.json").is_file()
        assert (runs_dir / "result.json").is_file()

        event_types = [e[0] for e in events]
        assert "run_started" in event_types
        assert "tool_result" in event_types
        assert "run_completed" in event_types

    async def test_progress_events_types(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify all expected event types are emitted."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        config = RuntimeConfig(max_steps=30)
        events: list[tuple[str, dict]] = []

        def callback(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        runner = initialize_components(
            config,
            fake=True,
            base_repo=str(baseline),
            on_event=callback,
        )
        runner.agent.llm_client = FakeLLMClient(_make_responses())

        task = load_issue(str(_ISSUE_PATH))
        await runner.run(task)

        event_types = [e[0] for e in events]
        assert "run_started" in event_types
        assert "agent_decision" in event_types
        assert "tool_called" in event_types
        assert "tool_result" in event_types
        assert "phase_changed" in event_types
        assert "run_completed" in event_types


class TestInitializeComponents:
    def test_initializes_without_errors(
        self, tmp_path: Path
    ) -> None:
        """Components initialize without errors."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        config = RuntimeConfig()
        runner = initialize_components(
            config, fake=True, base_repo=str(baseline)
        )
        assert runner is not None
        assert runner.config == config
        assert len(runner.registry.names) == 8

    def test_register_all_tools(self) -> None:
        """All 8 tools are registered."""
        registry = ToolRegistry()
        register_all_tools(registry)
        assert len(registry.names) == 8
        expected = {
            "repo.list_files",
            "repo.search_code",
            "repo.read_file",
            "code.apply_patch",
            "code.create_file",
            "test.run",
            "git.diff",
            "git.status",
        }
        assert set(registry.names) == expected


class TestCliInvocation:
    def test_cli_help(self) -> None:
        """CLI can be invoked and shows help."""
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "devpilot" in result.output.lower()

    def test_cli_run_help(self) -> None:
        """CLI run subcommand shows help."""
        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "issue" in result.output.lower()

    def test_cli_run_fake(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI run command works with --fake."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "run",
                str(_ISSUE_PATH),
                "--fake",
                "--base-repo",
                str(baseline),
            ],
        )
        assert result.exit_code == 0
        assert "DEV-001" in result.output
        assert "completed" in result.output
