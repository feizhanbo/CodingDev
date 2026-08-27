"""Tool: git.diff - show the working-tree diff."""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.path_guard import PathGuard


class GitDiffInput(BaseModel):
    """Input model for git.diff."""

    path: str | None = None


class GitDiff(Tool):
    """Show ``git diff`` for the whole workspace or a single path."""

    name = "git.diff"
    description = """\
name: git.diff
purpose: Show the unified diff of uncommitted changes in the workspace.
use_when:
  - you want to review what has been modified before verifying
  - you need the final diff for a report
avoid_when:
  - you only need to know which files changed; use git.status instead
constraints:
  - path (if given) must be inside workspace
  - shows unstaged working-tree changes only
"""
    input_model = GitDiffInput

    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        inp = args  # validated by registry as GitDiffInput
        cmd = ["git", "diff"]
        if inp.path:
            guard = PathGuard(ctx.workspace_root)
            try:
                guard.validate_path(inp.path)
            except PermissionError as exc:
                return ToolResult(success=False, error=str(exc))
            cmd += ["--", inp.path]

        stdout, stderr, code = await _run(cmd, ctx.workspace_root)
        if code != 0:
            return ToolResult(
                success=False,
                error=stderr.strip() or "git diff failed",
                data={"diff": ""},
            )
        return ToolResult(success=True, data={"diff": stdout})


async def _run(cmd: list[str], cwd: str) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    return (
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
        proc.returncode if proc.returncode is not None else 0,
    )
