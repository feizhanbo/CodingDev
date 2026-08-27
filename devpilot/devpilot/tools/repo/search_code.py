"""Tool: repo.search_code - search file contents via ripgrep (with fallback)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
from pathlib import Path

from pydantic import BaseModel

from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.path_guard import PathGuard

SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "node_modules",
    ".pytest_cache", ".ruff_cache",
}
# ripgrep output line:  path:line_number:text
_RG_LINE = re.compile(r"^(.+?):(\d+):(.*)$")


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
        inp = args  # validated by registry as SearchCodeInput
        guard = PathGuard(ctx.workspace_root)
        try:
            resolved = guard.validate_path(inp.path)
        except PermissionError as exc:
            return ToolResult(success=False, error=str(exc))

        rg = shutil.which("rg")
        if rg is not None:
            matches, truncated = await self._run_rg(
                rg, inp, resolved, ctx.workspace_root
            )
        else:
            matches, truncated = await asyncio.to_thread(
                self._python_search,
                inp.query,
                resolved,
                Path(ctx.workspace_root),
                inp.glob,
                inp.max_results,
            )

        return ToolResult(
            success=True,
            data={"matches": matches, "truncated": truncated},
        )

    async def _run_rg(
        self,
        rg: str,
        inp: SearchCodeInput,
        resolved: Path,
        workspace_root: str,
    ) -> tuple[list[dict[str, object]], bool]:
        cmd = [
            rg, "--line-number", "--no-heading",
            "--with-filename", "--color=never",
        ]
        if inp.glob:
            cmd += ["--glob", inp.glob]
        cmd += ["--", inp.query, str(resolved)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_root,
        )
        stdout, _ = await proc.communicate()
        text = stdout.decode(errors="replace")
        matches: list[dict[str, object]] = []
        for line in text.splitlines():
            m = _RG_LINE.match(line)
            if not m:
                continue
            path_str = m.group(1)
            with contextlib.suppress(ValueError):
                path_str = str(
                    Path(path_str)
                    .relative_to(workspace_root)
                    .as_posix()
                )
            matches.append({
                "path": path_str,
                "line": int(m.group(2)),
                "text": m.group(3),
            })
            if len(matches) >= inp.max_results:
                return matches, True
        return matches, False

    def _python_search(
        self,
        query: str,
        root: Path,
        workspace_root: Path,
        glob: str | None,
        max_results: int,
    ) -> tuple[list[dict[str, object]], bool]:
        """Fallback search when ripgrep is unavailable."""
        matches: list[dict[str, object]] = []
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                fpath = Path(dirpath) / fname
                if glob and not fpath.match(glob):
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if query in line:
                        matches.append({
                            "path": _relative(fpath, workspace_root),
                            "line": i,
                            "text": line,
                        })
                        if len(matches) >= max_results:
                            return matches, True
        return matches, False


def _relative(path: Path, workspace_root: Path) -> str:
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return path.as_posix()
