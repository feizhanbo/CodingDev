"""Tool: repo.read_file - read a UTF-8 source file with line numbers."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from devpilot.execution import execution_scope
from devpilot.processes import run_cancellable
from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.path_guard import PathGuard
from devpilot.tools.repo.file_cache import ReadFileCache
from devpilot.tools.repo.streaming import bounded_lines, content_digest

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

    def __init__(self) -> None:
        self.cache = ReadFileCache()

    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        # Authorize EVERY access, including cache hits, before opening any content.
        try:
            resolved = PathGuard(ctx.workspace_root).validate_path(args.path)
            if not resolved.is_file():
                return ToolResult(success=False, error=f"Not a file: {args.path}")
            return await run_cancellable(self._read, resolved, args, ctx)
        except (OSError, UnicodeError) as exc:
            return ToolResult(success=False, error=str(exc))

    def _read(self, path, args, ctx, *, cancel):
        with execution_scope(cancel=cancel, deadline=ctx.deadline):
            key = (
                str(path),
                args.start_line,
                args.end_line,
                content_digest(path),
                ctx.max_output_bytes,
            )
            cached = self.cache.get(key)
            if cached is not None:
                return cached
            start = max(1, args.start_line or 1)
            end = max(start, args.end_line) if args.end_line is not None else None
            # Reserve JSON metadata and worst-case JSON escaping space.
            limit = max(1, (ctx.max_output_bytes - 1024) // 6)
            numbered = []
            used = 0
            truncated = False
            for number, line, clipped in bounded_lines(path, limit):
                if number < start:
                    continue
                if end is not None and number > end:
                    break
                rendered = f"{number:>4}{ARROW}{line}"
                size = len(rendered.encode("utf-8")) + 1
                if len(numbered) >= MAX_LINES or used + size > limit:
                    available = max(0, limit - used - 1)
                    if available and len(numbered) < MAX_LINES:
                        numbered.append(
                            rendered.encode("utf-8")[:available].decode("utf-8", errors="ignore")
                        )
                    truncated = True
                    break
                numbered.append(rendered)
                used += size
                truncated |= clipped
            content = "\n".join(numbered)
            if truncated:
                content += "\n... (truncated)"
            result = ToolResult(
                success=True,
                data={
                    "path": _relative(path, ctx.workspace_root),
                    "start_line": start,
                    "end_line": start + len(numbered) - 1,
                    "content": content,
                    "truncated": truncated,
                },
            )
            self.cache.put(key, result)
            return result


def _relative(path: Path, workspace_root: str) -> str:
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return path.as_posix()
