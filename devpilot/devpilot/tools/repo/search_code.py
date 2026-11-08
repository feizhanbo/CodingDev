"""Tool: repo.search_code - search file contents via ripgrep (with fallback)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pydantic import BaseModel

from devpilot.processes import capture_process_async, run_sync
from devpilot.security import permitted_files
from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.path_guard import PathGuard
from devpilot.tools.repo.streaming import bounded_lines

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
}


class SearchCodeInput(BaseModel):
    """Input model for repo.search_code."""

    query: str
    path: str = "."
    glob: str | None = None
    max_results: int = 50


class SearchCode(Tool):
    """Search file contents for a query string."""

    name = "repo.search_code"
    description = """\
name: repo.search_code
purpose: Search file contents in the workspace for a query string.
use_when:
  - you need to locate where a symbol or string is used
  - you need to find candidate files before reading them
avoid_when:
  - you already know the file path; use repo.read_file directly
constraints:
  - path must be inside workspace
  - case-sensitive substring match
  - maximum max_results matches returned (truncated flag set if exceeded)
"""
    input_model = SearchCodeInput

    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        guard = PathGuard(ctx.workspace_root)
        try:
            root = guard.validate_path(args.path)
            files = permitted_files(root, Path(ctx.workspace_root).resolve())
            if args.glob:
                files = [p for p in files if p.match(args.glob)]
            if args.max_results <= 0:
                raise ValueError("max_results must be positive")
            rg = shutil.which("rg")
            matches = []
            truncated = False
            # Bound command length on Windows; filter BEFORE reading file contents.
            for path in files:
                if rg:
                    try:
                        proc = await capture_process_async(
                            [
                                rg,
                                "--json",
                                "--fixed-strings",
                                "--max-columns",
                                "4096",
                                "--max-count",
                                str(args.max_results + 1),
                                "--",
                                args.query,
                                str(path),
                            ],
                            cwd=ctx.workspace_root,
                            output_limit=ctx.max_output_bytes,
                        )
                    except ValueError as exc:
                        if "output_limit" not in str(exc):
                            raise
                        return ToolResult(
                            success=True, data={"matches": matches, "truncated": True}
                        )
                    if proc.returncode not in (0, 1):
                        raise RuntimeError(proc.stderr)
                    stdout = proc.stdout
                    lines = []
                    for line in stdout.splitlines():
                        item = json.loads(line)
                        if item["type"] == "match":
                            data = item["data"]
                            lines.append(
                                (data["line_number"], data["lines"]["text"].rstrip("\r\n"))
                            )
                else:

                    def search(path=path):
                        found = []
                        clipped_any = False
                        for number, line, clipped in bounded_lines(path, 4096):
                            clipped_any |= clipped
                            if args.query in line:
                                found.append((number, line))
                            if len(found) > args.max_results:
                                break
                        return found, clipped_any

                    try:
                        lines, clipped = await run_sync(search)
                        truncated |= clipped
                    except (UnicodeError, OSError):
                        continue
                for number, line in lines:
                    matches.append(
                        {
                            "path": path.relative_to(Path(ctx.workspace_root).resolve()).as_posix(),
                            "line": number,
                            "text": line,
                        }
                    )
                    if len(json.dumps(matches).encode("utf-8")) > max(
                        0, ctx.max_output_bytes - 1024
                    ):
                        matches.pop()
                        return ToolResult(
                            success=True, data={"matches": matches, "truncated": True}
                        )
                    if len(matches) > args.max_results:
                        return ToolResult(
                            success=True,
                            data={"matches": matches[: args.max_results], "truncated": True},
                        )
            return ToolResult(success=True, data={"matches": matches, "truncated": truncated})
        except (PermissionError, ValueError, RuntimeError, OSError) as exc:
            return ToolResult(success=False, error=str(exc))
