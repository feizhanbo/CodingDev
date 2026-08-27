"""DevPilot command-line interface."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from devpilot.agents.developer import DeveloperAgent
from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
from devpilot.domain.result import AgentRunResult
from devpilot.domain.task import DevelopmentTask
from devpilot.llm.base import LLMResponse
from devpilot.llm.config import LLMConfig
from devpilot.llm.fake import FakeLLMClient
from devpilot.llm.openai import OpenAIClient
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.runtime.custom.loop_guard import LoopGuard
from devpilot.runtime.custom.runner import CustomAgentRunner
from devpilot.runtime.custom.state_manager import StateManager
from devpilot.tools.code.apply_patch import ApplyPatch
from devpilot.tools.code.create_file import CreateFile
from devpilot.tools.git.diff import GitDiff
from devpilot.tools.git.status import GitStatus
from devpilot.tools.registry import ToolRegistry
from devpilot.tools.repo.list_files import ListFiles
from devpilot.tools.repo.read_file import ReadFile
from devpilot.tools.repo.search_code import SearchCode
from devpilot.tools.test.run_tests import RunTests
from devpilot.workspace.config import WorkspaceConfig
from devpilot.workspace.sandbox import SandboxWorkspace

app = typer.Typer(name="devpilot", help="DevPilot - AI Development Task Agent")
console = Console()


@app.callback()
def _callback() -> None:
    """DevPilot - AI Development Task Agent."""


def load_issue(path: str) -> DevelopmentTask:
    """Load a development issue from a YAML file.

    Maps YAML fields to :class:`DevelopmentTask` and records the source
    file path in ``metadata``.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Issue file not found: {path}")
    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid issue YAML (expected mapping): {path}")
    required = {"id", "title", "description", "acceptance_criteria"}
    missing = required - set(data)
    if missing:
        raise ValueError(
            f"Issue YAML missing required fields: {sorted(missing)}"
        )
    metadata = dict(data.get("metadata") or {})
    metadata["issue_file"] = str(p.resolve())
    return DevelopmentTask(
        id=data["id"],
        title=data["title"],
        description=data["description"],
        acceptance_criteria=list(data.get("acceptance_criteria", [])),
        constraints=list(data.get("constraints", [])),
        metadata=metadata,
    )


def register_all_tools(registry: ToolRegistry) -> None:
    """Register all eight DevPilot tools onto *registry*."""
    registry.register(ListFiles())
    registry.register(SearchCode())
    registry.register(ReadFile())
    registry.register(ApplyPatch())
    registry.register(CreateFile())
    registry.register(RunTests())
    registry.register(GitDiff())
    registry.register(GitStatus())


def create_fake_client() -> FakeLLMClient:
    """Create a FakeLLMClient with a default response sequence for testing."""
    responses = [
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="repo.search_code", arguments={"query": "def"}
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="code.create_file",
                    arguments={
                        "path": "test_smoke.py",
                        "content": "def test_smoke():\n    assert True\n",
                    },
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="test.run", arguments={"target": "test_smoke.py"}
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                finish=FinishIntent(
                    summary="Smoke test added", risk="low"
                )
            ),
            model="fake",
        ),
    ]
    return FakeLLMClient(responses)


def initialize_components(
    config: RuntimeConfig,
    fake: bool = False,
    base_repo: str | None = None,
    on_event: Callable[[str, dict], None] | None = None,
) -> CustomAgentRunner:
    """Initialize all DevPilot components and return a ready runner."""
    # 1. LLM Client
    llm_client = (
        create_fake_client() if fake else OpenAIClient(config=LLMConfig())
    )

    # 2. Tool Registry
    registry = ToolRegistry()
    register_all_tools(registry)

    # 3. Sandbox
    ws_config = WorkspaceConfig()
    sandbox = SandboxWorkspace(
        base_repo_path=base_repo or ws_config.base_repo,
        workspace_root=ws_config.workspace_root,
        runs_root=ws_config.runs_root,
    )

    # 4. Runtime components
    state_manager = StateManager(config)
    context_builder = ContextBuilder(config, registry)
    loop_guard = LoopGuard(config)
    agent = DeveloperAgent(llm_client, registry)

    return CustomAgentRunner(
        agent=agent,
        registry=registry,
        sandbox=sandbox,
        state_manager=state_manager,
        context_builder=context_builder,
        loop_guard=loop_guard,
        config=config,
        on_event=on_event,
    )


def _format_tool_result(tool: str, success: bool, data: dict | None) -> str:
    """Format a tool result into a concise one-line summary."""
    if data is None:
        return "OK" if success else "failed"
    if tool == "test.run":
        passed = data.get("passed")
        failed = data.get("failed")
        if passed is not None or failed is not None:
            return f"pytest: {failed or 0} failed, {passed or 0} passed"
        return "pytest: done" if success else "pytest: failed"
    if tool == "code.apply_patch":
        files = data.get("modified_files") or []
        if files:
            return f"patch applied: {', '.join(files)}"
        return "patch applied" if success else "patch failed"
    if tool == "code.create_file":
        path = data.get("path", "?")
        return f"file created: {path}" if success else f"create failed: {path}"
    if tool.startswith("repo.") or tool.startswith("git."):
        return "OK" if success else "failed"
    return "OK" if success else "failed"


def _make_rich_callback(
    task_id: str, verbose: bool = False
) -> Callable[[str, dict], None]:
    """Create a progress-event callback that prints Rich-formatted lines."""
    # Rich interprets [..] as markup tags; escape the literal brackets.
    prefix = f"\\[{task_id}]"

    def callback(event_type: str, data: dict) -> None:
        if event_type == "run_started":
            phase = data.get("phase", "")
            count = data.get("acceptance_criteria_count", 0)
            console.print(
                f"[bold cyan]{prefix}[/] {phase:<12} "
                f"-> parsed {count} acceptance criteria"
            )
        elif event_type == "phase_changed" and verbose:
            new_phase = data.get("to", "")
            old_phase = data.get("from", "")
            console.print(
                f"[bold]{prefix}[/] {new_phase:<12} "
                f"-> phase: {old_phase} -> {new_phase}"
            )
        elif event_type == "tool_called" and verbose:
            phase = data.get("phase", "")
            tool = data.get("tool", "")
            args = data.get("arguments", {})
            arg_str = ", ".join(repr(v) for v in args.values())
            console.print(
                f"{prefix} {phase:<12} -> {tool}({arg_str})"
            )
        elif event_type == "tool_result":
            phase = data.get("phase", "")
            tool = data.get("tool", "")
            success = data.get("success", False)
            data_dict = data.get("data")
            summary = _format_tool_result(tool, success, data_dict)
            color = "green" if success else "red"
            console.print(
                f"{prefix} {phase:<12} "
                f"-> [{color}]{summary}[/]"
            )
        elif event_type == "run_completed":
            console.print(
                f"[bold green]{prefix}[/] {'completed':<12} "
                f"-> success"
            )
        elif event_type == "run_failed":
            error = data.get("error", "unknown")
            console.print(
                f"[bold red]{prefix}[/] {'failed':<12} -> {error}"
            )

    return callback


def _display_summary(
    result: AgentRunResult, task: DevelopmentTask
) -> None:
    """Display a Rich table with the final run summary."""
    table = Table(title=f"DevPilot Run Summary: {result.run_id}")
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value")

    table.add_row("Task ID", result.task_id)
    table.add_row("Title", task.title)
    status_style = (
        "green" if result.status == "completed" else "red"
    )
    table.add_row(
        "Status", f"[{status_style}]{result.status}[/]"
    )
    table.add_row("Total Steps", str(result.total_steps))
    table.add_row(
        "Modified Files",
        ", ".join(result.modified_files) if result.modified_files else "(none)",
    )
    table.add_row(
        "Duration",
        f"{result.duration_ms} ms" if result.duration_ms else "N/A",
    )
    table.add_row(
        "Risk Level", result.risk or "N/A"
    )
    table.add_row(
        "Summary", result.summary or result.error or "N/A"
    )

    console.print(table)


@app.command()
def run(
    issue_file: str = typer.Argument(
        ..., help="Path to issue YAML file"
    ),
    fake: bool = typer.Option(
        False, "--fake", help="Use FakeLLMClient for testing"
    ),
    base_repo: str = typer.Option(
        None, "--base-repo", help="Override base repo path"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Verbose output"
    ),
) -> None:
    """Run DevPilot on a development issue."""
    # 1. Load issue from YAML
    task = load_issue(issue_file)
    console.print(
        f"[bold]Loaded issue:[/] {task.id} - {task.title}"
    )

    # 2. Initialize components
    config = RuntimeConfig()
    callback = _make_rich_callback(task.id, verbose=verbose)
    runner = initialize_components(
        config, fake=fake, base_repo=base_repo, on_event=callback
    )

    # 3. Run agent
    result = asyncio.run(runner.run(task))

    # 4. Display results
    _display_summary(result, task)

    # 5. Exit code
    if result.status != "completed":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
