"""Tool: repo.list_files - list files and directories in the workspace tree."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from devpilot.security import forbidden, linked
from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.path_guard import PathGuard

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
}
MAX_ENTRIES = 200


class ListFilesInput(BaseModel):
    """Input model for repo.list_files."""

    path: str = "."
    depth: int = Field(default=3, ge=1, le=10)


class ListFiles(Tool):
    """List files and directories up to a configurable depth."""

    name = "repo.list_files"
    description = """\
name: repo.list_files
purpose: List files and directories in the workspace tree up to a given depth.
use_when:
  - you need to understand the project structure before reading specific files
  - you need to find candidate files for a task
avoid_when:
  - you already know the exact file path; use repo.read_file directly
constraints:
  - path must be inside workspace
  - maximum 200 entries returned (truncated flag set if exceeded)
  - .git, __pycache__, .venv, node_modules are skipped
"""
    input_model = ListFilesInput

    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        inp = args  # validated by registry as ListFilesInput
        guard = PathGuard(ctx.workspace_root)
        try:
            resolved = guard.validate_path(inp.path)
        except PermissionError as exc:
            return ToolResult(success=False, error=str(exc))

        if not resolved.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {inp.path}")

        workspace = Path(ctx.workspace_root)
        entries = await asyncio.to_thread(_walk_sync, resolved, workspace, inp.depth)
        truncated = False
        if len(entries) > MAX_ENTRIES:
            entries = entries[:MAX_ENTRIES]
            truncated = True

        return ToolResult(
            success=True,
            data={"entries": entries, "truncated": truncated},
        )


def _walk_sync(root: Path, workspace_root: Path, max_depth: int) -> list[dict[str, str]]:
    """Depth-limited DFS returning ``{path, type}`` entries."""
    entries: list[dict[str, str]] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name)
        except (PermissionError, OSError):
            continue
        for child in children:
            name = child.name
            if linked(child) or forbidden(child.relative_to(workspace_root).as_posix()):
                continue
            try:
                rel = child.relative_to(workspace_root).as_posix()
            except ValueError:
                rel = child.as_posix()
            if child.is_dir():
                if name in SKIP_DIRS:
                    continue
                entries.append({"path": rel, "type": "dir"})
                if depth + 1 < max_depth:
                    stack.append((child, depth + 1))
            else:
                entries.append({"path": rel, "type": "file"})
    return entries
