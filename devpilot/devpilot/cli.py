"""DevPilot command-line interface."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from devpilot.agents.developer import DeveloperAgent
from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
from devpilot.domain.result import AgentRunResult
from devpilot.domain.task import DevelopmentTask
from devpilot.llm.base import LLMResponse
from devpilot.llm.fake import FakeLLMClient
from devpilot.llm.openai import OpenAIClient
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.runtime.custom.loop_guard import LoopGuard
from devpilot.runtime.custom.runner import CustomAgentRunner
from devpilot.runtime.custom.state_manager import StateManager
from devpilot.settings import Settings
from devpilot.tools.code.apply_patch import ApplyPatch
from devpilot.tools.code.create_file import CreateFile
from devpilot.tools.git.diff import GitDiff
from devpilot.tools.git.status import GitStatus
from devpilot.tools.registry import ToolRegistry
from devpilot.tools.repo.list_files import ListFiles
from devpilot.tools.repo.read_file import ReadFile
from devpilot.tools.repo.search_code import SearchCode
from devpilot.tools.test.run_tests import RunTests
from devpilot.tracing import MetricsCollector, TraceWriter
from devpilot.verification import TaskVerifier
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
        raise ValueError(f"Issue YAML missing required fields: {sorted(missing)}")
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


def register_all_tools(registry: ToolRegistry, settings: Settings | None = None) -> None:
    """Register all eight DevPilot tools onto *registry*."""
    registry.register(ListFiles())
    registry.register(SearchCode())
    registry.register(ReadFile())
    registry.register(ApplyPatch())
    registry.register(CreateFile())
    settings = settings or Settings()
    registry.register(
        RunTests(
            settings.test_python,
            settings.test_timeout_seconds,
            settings.runs_root,
            output_limit_bytes=settings.max_test_output_bytes,
        )
    )
    registry.register(GitDiff())
    registry.register(GitStatus())


def smoke_repository() -> str:
    return str(files("devpilot") / "fixtures" / "smoke")


def create_fake_client() -> FakeLLMClient:
    """Exercise a genuine code edit, failure, repair, added test and verification."""

    def patch(before: str, after: str) -> dict:
        return {
            "patch": "--- a/calculator.py\n+++ b/calculator.py\n@@ -4 +4 @@\n"
            f"-    return {before}\n+    return {after}\n"
        }

    actions = [
        ToolAction(tool="repo.search_code", arguments={"query": "add"}),
        ToolAction(tool="repo.read_file", arguments={"path": "calculator.py"}),
        ToolAction(tool="code.apply_patch", arguments=patch("0", "a - b")),
        ToolAction(tool="test.run", arguments={}),
        ToolAction(tool="code.apply_patch", arguments=patch("a - b", "a + b")),
        ToolAction(
            tool="code.create_file",
            arguments={
                "path": "tests/test_addition_edges.py",
                "content": (
                    "from calculator import add\n\ndef test_zero():\n    assert add(0, 9) == 9\n"
                ),
            },
        ),
        ToolAction(tool="test.run", arguments={}),
    ]
    responses = [LLMResponse(model="fake", decision=AgentDecision(action=a)) for a in actions]
    responses.append(
        LLMResponse(
            model="fake",
            decision=AgentDecision(
                finish=FinishIntent(summary="Runtime smoke: addition repaired", risk="low")
            ),
        )
    )
    return FakeLLMClient(responses)


def initialize_components(
    config: RuntimeConfig | None = None,
    fake: bool = False,
    base_repo: str | None = None,
    on_event: Callable[[str, dict], None] | None = None,
    settings: Settings | None = None,
) -> CustomAgentRunner:
    """Initialize all DevPilot components and return a ready runner."""
    settings = settings or Settings()
    config = config or settings.runtime_config()
    settings = settings.model_copy(
        update={name: getattr(config, name) for name in config.__dataclass_fields__}
    )
    # 1. LLM Client
    llm_client = create_fake_client() if fake else OpenAIClient(config=settings.llm_config())

    # 2. Tool Registry
    registry = ToolRegistry()
    register_all_tools(registry, settings)

    # 3. Sandbox
    ws_config = settings.workspace_config()
    sandbox = SandboxWorkspace(
        base_repo_path=(base_repo or (smoke_repository() if fake else ws_config.base_repo)),
        workspace_root=ws_config.workspace_root,
        runs_root=ws_config.runs_root,
    )

    sandbox.secrets = (settings.api_key,)
    sandbox.max_bytes = settings.workspace_max_bytes
    sandbox.total_max_bytes = settings.workspace_total_max_bytes
    sandbox.artifacts_max_bytes = settings.run_artifacts_max_bytes
    sandbox.artifacts_total_max_bytes = settings.runs_total_max_bytes
    test_tool = registry.get("test.run")
    test_tool.secrets = sandbox.secrets

    # 4. Runtime components
    state_manager = StateManager(config)
    context_builder = ContextBuilder(config, registry)
    loop_guard = LoopGuard(config)
    agent = DeveloperAgent(llm_client, registry)

    # 5. Verifier and tracing
    verifier = TaskVerifier(config)
    trace_writer = TraceWriter(ws_config.runs_root)
    trace_writer.secrets = sandbox.secrets
    context_builder.trace_writer = trace_writer
    metrics = MetricsCollector()

    return CustomAgentRunner(
        agent=agent,
        registry=registry,
        sandbox=sandbox,
        state_manager=state_manager,
        context_builder=context_builder,
        loop_guard=loop_guard,
        config=config,
        on_event=on_event,
        verifier=verifier,
        trace_writer=trace_writer,
        metrics=metrics,
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


def _make_rich_callback(task_id: str, verbose: bool = False) -> Callable[[str, dict], None]:
    """Create a progress-event callback that prints Rich-formatted lines."""
    # Rich interprets [..] as markup tags; escape the literal brackets.
    prefix = f"\\[{task_id}]"

    def callback(event_type: str, data: dict) -> None:
        if event_type == "run_started":
            phase = data.get("phase", "")
            count = data.get("acceptance_criteria_count", 0)
            console.print(
                f"[bold cyan]{prefix}[/] {phase:<12} -> parsed {count} acceptance criteria"
            )
        elif event_type == "phase_changed" and verbose:
            new_phase = data.get("to", "")
            old_phase = data.get("from", "")
            console.print(f"[bold]{prefix}[/] {new_phase:<12} -> phase: {old_phase} -> {new_phase}")
        elif event_type == "tool_called" and verbose:
            phase = data.get("phase", "")
            tool = data.get("tool", "")
            args = data.get("arguments", {})
            arg_str = ", ".join(repr(v) for v in args.values())
            console.print(f"{prefix} {phase:<12} -> {tool}({arg_str})")
        elif event_type == "tool_result":
            phase = data.get("phase", "")
            tool = data.get("tool", "")
            success = data.get("success", False)
            data_dict = data.get("data")
            summary = _format_tool_result(tool, success, data_dict)
            color = "green" if success else "red"
            console.print(f"{prefix} {phase:<12} -> [{color}]{summary}[/]")
        elif event_type == "verifier_started":
            phase = data.get("phase", "")
            console.print(f"[bold magenta]{prefix}[/] {phase:<12} -> verifier running")
        elif event_type == "verifier_result":
            phase = data.get("phase", "")
            success = data.get("success", False)
            reason = data.get("failure_reason", "")
            if success:
                console.print(f"[bold green]{prefix}[/] {phase:<12} -> verifier passed")
            else:
                console.print(f"[bold red]{prefix}[/] {phase:<12} -> verifier rejected: {reason}")
        elif event_type == "run_completed":
            console.print(f"[bold green]{prefix}[/] {'completed':<12} -> success")
        elif event_type == "run_failed":
            error = data.get("error", "unknown")
            console.print(f"[bold red]{prefix}[/] {'failed':<12} -> {error}")

    return callback


def _display_summary(result: AgentRunResult, task: DevelopmentTask) -> None:
    """Display a Rich table with the final run summary."""
    table = Table(title=f"DevPilot Run Summary: {result.run_id}")
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value")

    table.add_row("Task ID", result.task_id)
    table.add_row("Title", task.title)
    status_style = "green" if result.status == "completed" else "red"
    table.add_row("Status", f"[{status_style}]{result.status}[/]")
    table.add_row("Total Steps", str(result.total_steps))
    table.add_row(
        "Modified Files",
        ", ".join(result.modified_files) if result.modified_files else "(none)",
    )
    table.add_row(
        "Duration",
        f"{result.duration_ms} ms" if result.duration_ms else "N/A",
    )
    table.add_row("Risk Level", result.risk or "N/A")
    if result.artifact_errors:
        table.add_row("Artifact errors", ", ".join(result.artifact_errors))
        table.add_row("Recovery file", result.recovery_file or "unavailable")
    table.add_row("Summary", result.summary or result.error or "N/A")

    console.print(table)


@app.command()
def run(
    issue_file: str = typer.Argument(..., help="Path to issue YAML file"),
    fake: bool = typer.Option(False, "--fake", help="Use FakeLLMClient for testing"),
    base_repo: str = typer.Option(None, "--base-repo", help="Override base repo path"),
    test_python: str | None = typer.Option(None, help="Target pytest Python interpreter"),
    env_file: str = typer.Option(".env", help="Configuration dotenv file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Run DevPilot on a development issue."""
    # 1. Load issue from YAML
    task = load_issue(issue_file)
    console.print(f"[bold]Loaded issue:[/] {task.id} - {task.title}")

    # 2. Initialize components
    overrides = {"test_python": test_python} if test_python else {}
    settings = Settings(_env_file=env_file, **overrides)
    config = settings.runtime_config()
    callback = _make_rich_callback(task.id, verbose=verbose)
    runner = initialize_components(
        config,
        fake=fake,
        base_repo=None if fake else base_repo,
        on_event=callback,
        settings=settings,
    )

    if fake:
        console.print("Runtime smoke uses the bundled fixture; it is not a capability evaluation.")

    # 3. Run agent
    result = asyncio.run(runner.run(task))

    # 4. Display results
    _display_summary(result, task)

    # 5. Exit code
    if result.status != "completed":
        raise typer.Exit(code=1)


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="Interrupted ordinary run ID"),
    test_python: str | None = typer.Option(None, help="Original target pytest interpreter"),
    env_file: str = typer.Option(".env", help="Original configuration dotenv file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Resume a compatible checkpoint using its original budget and frozen evidence."""
    overrides = {"test_python": test_python} if test_python else {}
    settings = Settings(_env_file=env_file, **overrides)
    runner = initialize_components(settings=settings, on_event=_make_rich_callback(run_id, verbose))
    try:
        result = asyncio.run(runner.resume(run_id))
    except (OSError, ValueError, RuntimeError) as exc:
        from devpilot.security import redact

        console.print(redact(str(exc), (settings.api_key,)), markup=False)
        raise typer.Exit(code=1) from None
    from devpilot.security import redact

    console.print_json(json=redact(result.model_dump_json(), (settings.api_key,)))
    if result.status != "completed":
        raise typer.Exit(code=1)


@app.command()
def inspect(
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    runs_dir: str | None = typer.Option(None, help="Runs directory"),
) -> None:
    """Inspect a run's state, trace, and artifacts."""
    settings = Settings()
    run_path = Path(runs_dir or settings.runs_root) / run_id
    if not run_path.is_dir():
        console.print(f"[red]Run directory not found: {run_path}[/]")
        raise typer.Exit(code=1)

    # 1. Load and display state.json
    state_file = run_path / "state.json"
    if state_file.is_file():
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        state_table = Table(title=f"State: {run_id}")
        state_table.add_column("Field", style="bold cyan")
        state_table.add_column("Value")
        state_table.add_row("Run ID", state_data.get("run_id", ""))
        state_table.add_row("Phase", state_data.get("phase", ""))
        state_table.add_row("Current Step", str(state_data.get("current_step", 0)))
        state_table.add_row("Total Steps", str(state_data.get("total_steps", 0)))
        state_table.add_row("Retry Count", str(state_data.get("retry_count", 0)))
        state_table.add_row(
            "Modified Files",
            ", ".join(state_data.get("modified_files", [])) or "(none)",
        )
        state_table.add_row(
            "Observations",
            str(len(state_data.get("observations", []))),
        )
        console.print(state_table)
    else:
        console.print("[yellow]state.json not found[/]")

    # 2. Load and display result.json
    result_file = run_path / "result.json"
    if result_file.is_file():
        result_data = json.loads(result_file.read_text(encoding="utf-8"))
        result_table = Table(title=f"Result: {run_id}")
        result_table.add_column("Field", style="bold cyan")
        result_table.add_column("Value")
        status = result_data.get("status", "")
        status_style = "green" if status == "completed" else "red"
        result_table.add_row("Status", f"[{status_style}]{status}[/]")
        result_table.add_row("Task ID", result_data.get("task_id", ""))
        result_table.add_row(
            "Modified Files",
            ", ".join(result_data.get("modified_files", [])) or "(none)",
        )
        result_table.add_row(
            "Duration",
            f"{result_data.get('duration_ms', 0)} ms",
        )
        result_table.add_row("Risk", result_data.get("risk", "N/A"))
        result_table.add_row(
            "Summary",
            result_data.get("summary", "N/A"),
        )
        if result_data.get("error"):
            result_table.add_row("Error", result_data.get("error", ""))
        metrics = result_data.get("metrics", {})
        if metrics:
            result_table.add_row("Tool Calls", str(metrics.get("tool_calls", 0)))
            result_table.add_row("Tool Failures", str(metrics.get("tool_failures", 0)))
            result_table.add_row("Test Retries", str(metrics.get("test_retries", 0)))
        console.print(result_table)
    else:
        console.print("[yellow]result.json not found[/]")

    # 3. Load and display trace.jsonl summary
    trace_file = run_path / "trace.jsonl"
    if trace_file.is_file():
        trace_lines = trace_file.read_text(encoding="utf-8").strip().splitlines()
        event_count = len(trace_lines)
        key_events: list[str] = []
        for line in trace_lines:
            try:
                event = json.loads(line)
                event_type = event.get("event", "")
                if event_type in (
                    "run_started",
                    "run_completed",
                    "run_failed",
                    "verifier_started",
                    "verifier_result",
                    "guardrail_triggered",
                ):
                    key_events.append(event_type)
            except json.JSONDecodeError:
                continue
        console.print(
            Panel(
                f"Total events: {event_count}\n"
                f"Key events: {', '.join(key_events) if key_events else '(none)'}",
                title=f"Trace: {run_id}",
            )
        )
    else:
        console.print("[yellow]trace.jsonl not found[/]")

    # 4. Check for final.diff
    diff_file = run_path / "final.diff"
    if diff_file.is_file():
        diff_content = diff_file.read_text(encoding="utf-8").strip()
        if diff_content:
            console.print(
                Panel(
                    diff_content[:2000] if len(diff_content) > 2000 else diff_content,
                    title=f"Diff: {run_id}",
                )
            )
        else:
            console.print("[dim]final.diff is empty[/]")


@app.command()
def diff(
    run_id: str = typer.Argument(..., help="Run ID to diff"),
    runs_dir: str | None = typer.Option(None, help="Runs directory"),
) -> None:
    """Show the final diff for a run."""
    settings = Settings()
    run_path = Path(runs_dir or settings.runs_root) / run_id

    # 1. Try loading final.diff from runs directory
    diff_file = run_path / "final.diff"
    diff_content = ""
    if diff_file.is_file():
        diff_content = diff_file.read_text(encoding="utf-8").strip()

    # 2. If not found or empty, try workspace git diff
    if not diff_content:
        workspace_path = Path(settings.workspace_root) / run_id / "repo"
        if workspace_path.is_dir():
            import subprocess

            result = subprocess.run(
                ["git", "diff", "HEAD", "--no-color"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            diff_content = result.stdout.strip()

    if not diff_content:
        console.print(f"[yellow]No diff found for run {run_id}[/]")
        raise typer.Exit(code=1)

    # 3. Display the diff
    console.print(
        Panel(
            diff_content,
            title=f"Diff: {run_id}",
            border_style="blue",
        )
    )


@app.command()
def eval(
    issue_id: str = typer.Argument(None, help="Issue ID to evaluate (e.g. DEV-001)"),
    all_issues: bool = typer.Option(False, "--all", help="Run all issues"),
    fake: bool = typer.Option(False, "--fake", help="Use FakeLLMClient"),
    base_repo: str = typer.Option(None, "--base-repo", help="Override base repo path"),
    test_python: str | None = typer.Option(None, help="Target pytest Python interpreter"),
    env_file: str = typer.Option(".env", help="Configuration dotenv file"),
    issues_dir: str | None = typer.Option(None, help="Override packaged issue directory"),
    hidden_tests_dir: str | None = typer.Option(None, help="Override hidden test directory"),
) -> None:
    """Run evaluation on issues."""
    from devpilot.evals.runner import EvalRunner

    overrides = {"test_python": test_python} if test_python else {}
    settings = Settings(_env_file=env_file, **overrides)
    ws_config = settings.workspace_config()
    from devpilot.evals.benchmark import packaged_baseline

    repo_path = base_repo or (ws_config.base_repo if issues_dir else str(packaged_baseline()))

    eval_runner = EvalRunner(
        base_repo_path=repo_path,
        settings=settings,
        issues_dir=issues_dir,
        hidden_tests_dir=hidden_tests_dir,
    )

    if all_issues:
        console.print("[bold]Running evaluation for all issues...[/]")
        results = asyncio.run(eval_runner.run_all(fake=fake))
    elif issue_id:
        console.print(f"[bold]Running evaluation for {issue_id}...[/]")
        results = [asyncio.run(eval_runner.run_eval(issue_id, fake=fake))]
    else:
        console.print("[red]Please specify an issue ID or use --all[/]")
        raise typer.Exit(code=1)

    # Display summary table
    summary = eval_runner.generate_summary(results)
    console.print(summary)

    # Exit code based on success
    if not results or not all(r.evaluation_status == "PASS" for r in results):
        raise typer.Exit(code=1)


@app.command("benchmark-check")
def benchmark_check(
    output: str = typer.Option(..., help="New directory for self-validation artifacts"),
    base_repo: str | None = typer.Option(None, help="Pinned ShopFlow repository"),
    test_python: str | None = typer.Option(None, help="Target pytest Python interpreter"),
    env_file: str = typer.Option(".env", help="Configuration dotenv file"),
    performance: bool = typer.Option(False, help="Also enforce the hardware latency gate"),
) -> None:
    """Validate all eight defective starting points and reference fixes without an LLM."""
    from devpilot.evals.benchmark import packaged_baseline, validate_benchmark

    settings = Settings(_env_file=env_file)
    summary = validate_benchmark(
        Path(base_repo).resolve() if base_repo else packaged_baseline(),
        Path(output).resolve(),
        test_python or settings.test_python,
        performance=performance,
    )
    if not summary["passed"]:
        raise typer.Exit(code=1)


@app.command("workspace-report")
def workspace_report(retention_days: int = typer.Option(7, min=1)) -> None:
    """Read-only capacity report; retain run evidence and never delete files."""
    import time

    from devpilot.security import permitted_files
    from devpilot.storage import tree_bytes

    settings = Settings()
    root = Path(settings.workspace_root).resolve()
    entries = []
    for folder in sorted(root.iterdir()) if root.exists() else []:
        if not folder.is_dir() or folder.is_symlink() or folder.is_junction():
            continue
        size = sum(p.stat().st_size for p in permitted_files(folder, root))
        result = Path(settings.runs_root) / folder.name / "result.json"
        closed = result.is_file()
        old = time.time() - folder.stat().st_mtime > retention_days * 86400
        entries.append(
            {
                "run_id": folder.name,
                "logical_bytes": size,
                "manual_archive_candidate": closed and old,
            }
        )
    artifacts = []
    runs = Path(settings.runs_root).resolve()
    for folder in sorted(runs.iterdir()) if runs.exists() else []:
        if not folder.is_dir() or folder.is_symlink() or folder.is_junction():
            continue
        old = time.time() - folder.stat().st_mtime > retention_days * 86400
        artifacts.append(
            {
                "run_id": folder.name,
                "physical_bytes": tree_bytes(folder),
                "manual_archive_candidate": (folder / "result.json").is_file() and old,
            }
        )
    console.print_json(
        data={
            "execution_mode": "trusted_local",
            "retention": "keep_all",
            "total_limit_bytes": settings.workspace_total_max_bytes,
            "workspaces": entries,
            "artifacts": artifacts,
            "artifacts_limit_bytes": settings.run_artifacts_max_bytes,
            "artifacts_total_limit_bytes": settings.runs_total_max_bytes,
        }
    )


if __name__ == "__main__":
    app()
