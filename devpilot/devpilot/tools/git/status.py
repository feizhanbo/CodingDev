"""Tool: git.status - show the porcelain status of the worktree."""

from __future__ import annotations

from pydantic import BaseModel

from devpilot.processes import capture_process_async
from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult


class GitStatusInput(BaseModel):
    """Input model for git.status (no parameters)."""


class GitStatus(Tool):
    """Show ``git status --porcelain`` and count modified files."""

    name = "git.status"
    description = """\
name: git.status
purpose: Show the porcelain status of uncommitted changes in the workspace.
use_when:
  - you need a quick list of which files changed
  - you want to decide what to diff or verify next
avoid_when:
  - you need the actual line-level changes; use git.diff instead
constraints:
  - takes no parameters
  - returns raw porcelain output plus a modified-file count
"""
    input_model = GitStatusInput

    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        stdout, stderr, code = await _run(["git", "status", "--porcelain"], ctx.workspace_root)
        if code != 0:
            return ToolResult(
                success=False,
                error=stderr.strip() or "git status failed",
                data={"status": "", "modified_count": 0},
            )
        lines = [ln for ln in stdout.splitlines() if ln.strip()]
        return ToolResult(
            success=True,
            data={"status": stdout, "modified_count": len(lines)},
        )


async def _run(cmd: list[str], cwd: str) -> tuple[str, str, int]:
    result = await capture_process_async(cmd, cwd=cwd)
    return result.stdout, result.stderr, result.returncode
