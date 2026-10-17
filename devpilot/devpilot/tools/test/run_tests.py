"""Tool: test.run - run pytest in the workspace and capture results."""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from pathlib import Path

from pydantic import BaseModel

from devpilot.security import process_environment, redact
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
  - full output is saved to a log file; summary is truncated to 2000 chars
"""
    input_model = RunTestsInput

    # Configurable per-instance; tests override this to keep suites fast.
    timeout_seconds: int = 120

    def __init__(
        self,
        python_executable: str | None = None,
        timeout_seconds: int = 120,
        runs_root: str = "./runs",
    ) -> None:
        self.secrets: tuple[str, ...] = ()
        self.python_executable = python_executable or sys.executable
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

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=ctx.workspace_root,
                env=process_environment(),
            )
        except (FileNotFoundError, OSError) as exc:
            return ToolResult(
                success=False,
                error=f"Failed to start pytest: {exc}",
                data={
                    "exit_code": -1,
                    "duration_ms": 0,
                    "summary": str(exc),
                    "log_file": "",
                    "passed": None,
                    "failed": None,
                },
            )

        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=ctx.test_timeout_seconds or self.timeout_seconds
            )
        except (TimeoutError, asyncio.CancelledError) as exc:
            await _kill_and_wait(proc)
            if isinstance(exc, asyncio.CancelledError):
                raise
            output = "Test timed out; no output captured."
            _write_log(log_path, output)
            elapsed = int((time.monotonic() - start) * 1000)
            return ToolResult(
                success=False,
                data={
                    "exit_code": -1,
                    "passed": None,
                    "failed": None,
                    "duration_ms": elapsed,
                    "summary": (
                        f"Test timed out after {ctx.test_timeout_seconds or self.timeout_seconds}s"
                    ),
                    "log_file": str(log_path),
                },
            )

        elapsed = int((time.monotonic() - start) * 1000)
        output = redact(stdout.decode(errors="replace"), self.secrets)
        _write_log(log_path, output)

        evidence = parse_junit(report_path, proc.returncode)
        summary = output[-SUMMARY_LIMIT:]

        return ToolResult(
            success=evidence.status == "PASS",
            data={
                "exit_code": proc.returncode,
                "passed": evidence.passed,
                "failed": evidence.failed,
                "collected": evidence.collected,
                "errors": evidence.errors,
                "skipped": evidence.skipped,
                "status": evidence.status,
                "report_file": str(report_path),
                "duration_ms": elapsed,
                "summary": summary,
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


def _write_log(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


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


async def _kill_and_wait(proc: asyncio.subprocess.Process) -> None:
    """Terminate a subprocess and reap it (safe inside a running loop)."""
    try:
        proc.kill()
    except ProcessLookupError:
        return
    await proc.wait()
