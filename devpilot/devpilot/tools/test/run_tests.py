"""Tool: test.run - run pytest in the workspace and capture results."""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

from pydantic import BaseModel

from devpilot.processes import run_process_async
from devpilot.security import process_environment
from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.path_guard import PathGuard

SUMMARY_LIMIT = 2000


class RunTestsInput(BaseModel):
    """Input model for test.run."""

    target: str | None = None
    extra_args: list[str] = []


class RunTests(Tool):
    """Run the pytest suite in the workspace with a timeout."""

    name = "test.run"
    description = """\
name: test.run
purpose: Run the pytest test suite in the active workspace.
use_when:
  - you have made changes and want to verify tests pass
  - you need to confirm a fix did not break existing tests
avoid_when:
  - you have not made any code changes yet
constraints:
  - executes pytest only; no other commands
  - runs with cwd set to the workspace root
  - a timeout is enforced (default 120s, configurable)
  - output is streamed to a bounded log; exceeding its limit fails the test run
  - summary is truncated to 2000 chars
"""
    input_model = RunTestsInput

    # Configurable per-instance; tests override this to keep suites fast.
    timeout_seconds: int = 120

    def __init__(
        self,
        python_executable: str | None = None,
        timeout_seconds: int = 120,
        runs_root: str = "./runs",
        output_limit_bytes: int = 2097152,
    ) -> None:
        self.output_limit_bytes = output_limit_bytes
        self.secrets: tuple[str, ...] = ()
        executable = python_executable or sys.executable
        self.python_executable = (
            str(Path(executable).resolve())
            if "/" in executable or "\\" in executable
            else executable
        )
        self.timeout_seconds = timeout_seconds
        self.runs_root = Path(runs_root).resolve()

    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        inp = args  # validated by registry as RunTestsInput
        from devpilot.evals.benchmark import parse_junit

        target = inp.target if inp.target else "."
        try:
            if target.startswith("-"):
                raise PermissionError("Test target cannot be a pytest option")
            PathGuard(ctx.workspace_root).validate_path(target.split("::", 1)[0])
            _validate_extra_args(inp.extra_args)
        except PermissionError as exc:
            return ToolResult(success=False, error=str(exc))
        log_path = _log_path(ctx, self.runs_root)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        report_path = log_path.with_suffix(".xml")
        cmd = [
            ctx.test_python or self.python_executable,
            "-m",
            "pytest",
            target,
            "-v",
            "--tb=short",
            *inp.extra_args,
            f"--junitxml={report_path}",
        ]

        timeout = ctx.test_timeout_seconds or self.timeout_seconds
        if ctx.deadline is not None:
            timeout = min(timeout, ctx.deadline - time.monotonic())
        if timeout <= 0:
            return ToolResult(success=False, error="Run deadline exceeded before pytest")
        try:
            process = await run_process_async(
                cmd,
                cwd=Path(ctx.workspace_root),
                env=process_environment(),
                log=log_path,
                timeout=timeout,
                output_limit=self.output_limit_bytes,
                secrets=self.secrets,
            )
        except (OSError, RuntimeError) as exc:
            return ToolResult(
                success=False,
                error=(
                    f"Failed to start pytest: {type(exc).__name__}"
                    if isinstance(exc, FileNotFoundError)
                    else f"Pytest process error: {type(exc).__name__}"
                ),
                data={
                    "exit_code": -1,
                    "passed": None,
                    "failed": None,
                    "log_file": str(log_path),
                    "duration_ms": 0,
                    "summary": str(exc),
                },
            )
        output = log_path.read_text(encoding="utf-8")
        if process.timed_out or process.output_limited:
            reason = (
                f"Test timed out after {timeout}s"
                if process.timed_out
                else "Test output limit exceeded"
            )
            return ToolResult(
                success=False,
                data={
                    "exit_code": -1,
                    "passed": None,
                    "failed": None,
                    "duration_ms": process.duration_ms,
                    "summary": reason,
                    "log_file": str(log_path),
                    "status": "ERROR",
                },
            )
        evidence = parse_junit(report_path, process.exit_code)
        return ToolResult(
            success=evidence.status == "PASS",
            data={
                "exit_code": process.exit_code,
                "passed": evidence.passed,
                "failed": evidence.failed,
                "collected": evidence.collected,
                "errors": evidence.errors,
                "skipped": evidence.skipped,
                "status": evidence.status,
                "report_file": str(report_path),
                "duration_ms": process.duration_ms,
                "summary": output[-SUMMARY_LIMIT:],
                "log_file": str(log_path),
            },
        )


def _log_path(ctx: ToolContext, runs_root: Path | None = None) -> Path:
    """Keep each invocation, including verifier retries, in the run artifact tree."""
    root = (
        Path(ctx.artifacts_dir)
        if ctx.artifacts_dir
        else ((runs_root or Path("./runs").resolve()) / ctx.run_id)
    )
    return root / "tests" / f"{uuid.uuid4().hex}.log"


def _validate_extra_args(arguments: list[str]) -> None:
    value_options = {"-k", "-m"}
    flags = {"-q", "-v", "-x", "--disable-warnings"}
    index = 0
    while index < len(arguments):
        arg = arguments[index]
        if arg in flags:
            index += 1
        elif arg in value_options and index + 1 < len(arguments):
            index += 2
        elif arg.startswith("--maxfail=") and arg.split("=", 1)[1].isdigit():
            index += 1
        else:
            raise PermissionError(f"Unsupported pytest argument: {arg}")
