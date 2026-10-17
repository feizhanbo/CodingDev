"""Tool: repo.search_code - search file contents via ripgrep (with fallback)."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from pydantic import BaseModel

from devpilot.security import permitted_files
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
            # Bound command length on Windows; filter BEFORE reading file contents.
            for path in files:
                if rg:
                    proc = await asyncio.create_subprocess_exec(
                        rg,
                        "--json",
                        "--fixed-strings",
                        "--",
                        args.query,
                        str(path),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=ctx.workspace_root,
                    )
                    stdout, stderr = await proc.communicate()
                    if proc.returncode not in (0, 1):
                        raise RuntimeError(stderr.decode(errors="replace"))
                    lines = []
                    for line in stdout.decode(errors="replace").splitlines():
                        item = json.loads(line)
                        if item["type"] == "match":
                            data = item["data"]
                            lines.append(
                                (data["line_number"], data["lines"]["text"].rstrip("\r\n"))
                            )
                else:
                    try:
                        content = await asyncio.to_thread(path.read_text, encoding="utf-8")
                    except (UnicodeDecodeError, OSError):
                        continue
                    lines = [
                        (i, line)
                        for i, line in enumerate(content.splitlines(), 1)
                        if args.query in line
                    ]
                for number, line in lines:
                    matches.append(
                        {
                            "path": path.relative_to(Path(ctx.workspace_root).resolve()).as_posix(),
                            "line": number,
                            "text": line,
                        }
                    )
                    if len(matches) > args.max_results:
                        return ToolResult(
                            success=True,
                            data={"matches": matches[: args.max_results], "truncated": True},
                        )
            return ToolResult(success=True, data={"matches": matches, "truncated": False})
        except (PermissionError, ValueError, RuntimeError, OSError) as exc:
            return ToolResult(success=False, error=str(exc))
