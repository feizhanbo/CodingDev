"""Tool: test.run - run pytest in the workspace and capture results."""

from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path

from pydantic import BaseModel

from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult

_PASSED_RE = re.compile(r"(\d+) passed")
_FAILED_RE = re.compile(r"(\d+) failed")
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

    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        inp = args  # validated by registry as RunTestsInput
        target = inp.target if inp.target else "."
        cmd = [
            sys.executable, "-m", "pytest", target,
            "-v", "--tb=short", *inp.extra_args,
        ]

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=ctx.workspace_root,
            )
        except (FileNotFoundError, OSError) as exc:
            return ToolResult(
                success=False,
                error=f"Failed to start pytest: {exc}",
                data={"exit_code": -1, "duration_ms": 0,
                      "summary": str(exc), "log_file": "",
                      "passed": None, "failed": None},
            )

        log_path = _log_path(ctx)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_seconds
            )
        except TimeoutError:
            await _kill_and_wait(proc)
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
                    "summary": f"Test timed out after {self.timeout_seconds}s",
                    "log_file": str(log_path),
                },
            )

        elapsed = int((time.monotonic() - start) * 1000)
        output = stdout.decode(errors="replace")
        _write_log(log_path, output)

        passed = _first_int(_PASSED_RE, output)
        failed = _first_int(_FAILED_RE, output)
        summary = output[-SUMMARY_LIMIT:]

        return ToolResult(
            success=proc.returncode == 0,
            data={
                "exit_code": proc.returncode,
                "passed": passed,
                "failed": failed,
                "duration_ms": elapsed,
                "summary": summary,
                "log_file": str(log_path),
            },
        )


def _log_path(ctx: ToolContext) -> Path:
    """Derive the run artifact log path from the workspace root."""
    return Path(ctx.workspace_root).parent / "runs" / ctx.run_id / "test-output.log"


def _write_log(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _first_int(pattern: re.Pattern[str], text: str) -> int | None:
    m = pattern.search(text)
    return int(m.group(1)) if m else None


async def _kill_and_wait(proc: asyncio.subprocess.Process) -> None:
    """Terminate a subprocess and reap it (safe inside a running loop)."""
    try:
        proc.kill()
    except ProcessLookupError:
        return
    await proc.wait()
