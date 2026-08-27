"""Tool: code.create_file - create a new file in the workspace."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.path_guard import PathGuard


class CreateFileInput(BaseModel):
    """Input model for code.create_file."""

    path: str
    content: str


class CreateFile(Tool):
    """Create a new UTF-8 file, creating parent directories as needed."""

    name = "code.create_file"
    description = """\
name: code.create_file
purpose: Create a new UTF-8 file in the workspace.
use_when:
  - you need to create a brand-new file that does not yet exist
  - you have full file content ready to write
avoid_when:
  - you want to modify an existing file; use code.apply_patch instead
constraints:
  - path must be inside workspace
  - forbidden files are denied by runtime
  - parent directories are created automatically
"""
    input_model = CreateFileInput

    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        inp = args  # validated by registry as CreateFileInput
        guard = PathGuard(ctx.workspace_root)
        try:
            resolved = guard.validate_path(inp.path)
        except PermissionError as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                data={"path": inp.path},
            )

        try:
            await asyncio.to_thread(_write_file, resolved, inp.content)
        except OSError as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                data={"path": inp.path},
            )

        rel = _relative(resolved, Path(ctx.workspace_root))
        return ToolResult(
            success=True,
            data={"path": rel, "error": None},
        )


def _write_file(path: Path, content: str) -> None:
    """Create parent dirs and write UTF-8 content (no newline translation)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _relative(path: Path, workspace_root: Path) -> str:
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return path.as_posix()
