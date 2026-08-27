"""Tool: repo.read_file - read a UTF-8 source file with line numbers."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.path_guard import PathGuard

MAX_LINES = 500
ARROW = "\u2192"  # →


class ReadFileInput(BaseModel):
    """Input model for repo.read_file."""

    path: str
    start_line: int | None = None
    end_line: int | None = None


class ReadFile(Tool):
    """Read a UTF-8 file from the workspace, adding line numbers."""

    name = "repo.read_file"
    description = """\
name: repo.read_file
purpose: Read a UTF-8 source file from the active workspace.
use_when:
  - you need exact implementation details before editing
  - search results identify a relevant file
avoid_when:
  - you only need to locate symbols; use repo.search_code first
constraints:
  - path must be inside workspace
  - forbidden files are denied by runtime
  - maximum 500 lines returned (truncated flag set if exceeded)
"""
    input_model = ReadFileInput

    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        inp = args  # validated by registry as ReadFileInput
        guard = PathGuard(ctx.workspace_root)
        try:
            resolved = guard.validate_path(inp.path)
        except PermissionError as exc:
            return ToolResult(success=False, error=str(exc))

        if not resolved.is_file():
            return ToolResult(success=False, error=f"Not a file: {inp.path}")

        try:
            raw = await asyncio.to_thread(
                resolved.read_text, encoding="utf-8"
            )
        except UnicodeDecodeError as exc:
            return ToolResult(
                success=False,
                error=f"File is not valid UTF-8: {inp.path} ({exc})",
            )
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))

        all_lines = raw.splitlines()
        start = (inp.start_line or 1)
        end = inp.end_line or len(all_lines)
        # clamp to valid range (1-indexed)
        start = max(1, start)
        end = min(len(all_lines), end)
        if end < start:
            end = start

        selected = all_lines[start - 1:end]
        truncated = False
        if len(selected) > MAX_LINES:
            selected = selected[:MAX_LINES]
            truncated = True

        numbered = [
            f"{start + i:>4}{ARROW}{line}" for i, line in enumerate(selected)
        ]
        content = "\n".join(numbered)
        if truncated:
            content += (
                f"\n... (truncated, showing {MAX_LINES} of "
                f"{end - start + 1} lines)"
            )

        rel = _relative(resolved, ctx.workspace_root)
        return ToolResult(
            success=True,
            data={
                "path": rel,
                "start_line": start,
                "end_line": start + len(selected) - 1,
                "content": content,
                "truncated": truncated,
            },
        )


def _relative(path: Path, workspace_root: str) -> str:
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return path.as_posix()
