"""Tool: code.apply_patch - apply a unified diff to the workspace."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel

from devpilot.processes import capture_process_async
from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.path_guard import PathGuard
from devpilot.verification.evidence import validate_write


class ApplyPatchInput(BaseModel):
    """Input model for code.apply_patch."""

    patch: str


class ApplyPatch(Tool):
    """Apply a unified diff to the workspace via ``git apply``."""

    name = "code.apply_patch"
    description = """\
name: code.apply_patch
purpose: Apply a unified diff patch to modify files in the workspace.
use_when:
  - you have prepared a unified diff and want to apply it
  - you need precise line-level edits to existing files
avoid_when:
  - you want to create a brand-new file; use code.create_file instead
constraints:
  - patch must be a unified diff
  - all target paths must be inside workspace
  - an empty patch is rejected
  - a context mismatch returns the git error message
"""
    input_model = ApplyPatchInput

    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        inp = args  # validated by registry as ApplyPatchInput
        # LLM may return patch with literal \n instead of actual newlines
        patch_text = inp.patch
        if "\n" not in patch_text and "\\n" in patch_text:
            patch_text = patch_text.replace("\\n", "\n")
        if not patch_text.strip():
            return ToolResult(
                success=False,
                error="empty patch",
                data={"modified_files": []},
            )

        paths = _extract_paths(patch_text)
        guard = PathGuard(ctx.workspace_root)
        for p in paths:
            try:
                guard.validate_path(p)
                validate_write(Path(ctx.workspace_root), p, ctx.trusted_root)
            except PermissionError as exc:
                return ToolResult(
                    success=False,
                    error=str(exc),
                    data={"modified_files": []},
                )

        patch_bytes = patch_text.encode("utf-8")
        if len(patch_bytes) > ctx.max_output_bytes:
            raise ValueError("patch_content_limit_exceeded: complete patch required")
        # Ask Git for its authoritative target paths, including binary changes.
        stat = await _run_git(
            ["git", "apply", "--numstat", "-z", "-"], cwd=ctx.workspace_root, stdin=patch_bytes
        )
        if stat.returncode:
            return ToolResult(success=False, error=stat.stderr, data={"modified_files": []})
        targets = [part.rsplit("\t", 1)[-1] for part in stat.stdout.split("\0") if part]
        if not targets:
            return ToolResult(
                success=False, error="Patch has no target files", data={"modified_files": []}
            )
        originals = {}
        original_bytes = 0
        for target in targets:
            resolved = guard.validate_path(target)
            validate_write(Path(ctx.workspace_root), target, ctx.trusted_root)
            original_bytes += resolved.stat().st_size if resolved.exists() else 0
            if original_bytes > ctx.max_output_bytes:
                raise ValueError("patch_content_limit_exceeded: complete rollback content required")
            originals[resolved] = resolved.read_bytes() if resolved.exists() else None
        last_error = "patch failed"
        try:
            for options in ([], ["--unidiff-zero"], ["--unidiff-zero", "--ignore-space-change"]):
                command = ["git", "apply", *options]
                check = await _run_git(
                    [*command, "--check", "-"], cwd=ctx.workspace_root, stdin=patch_bytes
                )
                if check.returncode:
                    last_error = check.stderr
                    continue
                result = await _run_git([*command, "-"], cwd=ctx.workspace_root, stdin=patch_bytes)
                if result.returncode:
                    raise RuntimeError(result.stderr)
                return ToolResult(
                    success=True,
                    data={
                        "modified_files": await _modified_files(ctx.workspace_root),
                        "error": None,
                    },
                )
        except BaseException:
            for path, original in originals.items():
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(original)
            raise
        return ToolResult(success=False, error=last_error, data={"modified_files": []})


class _GitResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


async def _run_git(cmd: list[str], cwd: str, stdin: bytes | None = None) -> _GitResult:
    """Run a git subprocess, returning decoded stdout/stderr."""
    result = await capture_process_async(cmd, cwd=cwd, stdin=stdin)
    return _GitResult(result.returncode, result.stdout, result.stderr)


async def _modified_files(workspace_root: str) -> list[str]:
    result = await _run_git(["git", "diff", "HEAD", "--name-only"], workspace_root)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _extract_paths(patch: str) -> list[str]:
    """Extract target file paths from a unified diff."""
    paths: list[str] = []
    for line in patch.splitlines():
        for prefix in ("+++ ", "--- "):
            if line.startswith(prefix):
                token = line[len(prefix) :].split(None, 1)
                if not token:
                    continue
                p = token[0]
                if p == "/dev/null":
                    continue
                if p.startswith("a/") or p.startswith("b/"):
                    p = p[2:]
                if p not in paths:
                    paths.append(p)
    return paths
