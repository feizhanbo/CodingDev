"""Tool: code.create_file - create a new file in the workspace."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.path_guard import PathGuard
from devpilot.verification.evidence import validate_write


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
            validate_write(Path(ctx.workspace_root), inp.path, ctx.trusted_root)
        except PermissionError as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                data={"path": inp.path, "modified_files": []},
            )

        try:
            await asyncio.to_thread(_write_file, resolved, inp.content)
        except OSError as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                data={"path": inp.path, "modified_files": []},
            )

        # Stage the file so it appears in ``git diff HEAD`` and is
        # tracked as a modified file by the state manager / verifier.
        await _git_add(ctx.workspace_root, str(resolved))

        rel = _relative(resolved, Path(ctx.workspace_root))
        return ToolResult(
            success=True,
            data={"path": rel, "error": None, "modified_files": [rel]},
        )


def _write_file(path: Path, content: str) -> None:
    """Create parent dirs and write UTF-8 content (no newline translation)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(content)


async def _git_add(workspace_root: str, file_path: str) -> None:
    """Stage a file so it appears in git diff HEAD."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        "add",
        "--",
        file_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workspace_root,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git add failed: {stderr.decode(errors='replace')}")


def _relative(path: Path, workspace_root: Path) -> str:
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return path.as_posix()
