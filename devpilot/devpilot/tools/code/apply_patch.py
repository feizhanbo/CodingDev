"""Tool: code.apply_patch - apply a unified diff to the workspace."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel

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

        # Try applying with progressively more lenient options.
        apply_attempts = [
            # git apply with fuzzy context and whitespace fix
            (["git", "apply", "--whitespace=fix", "-C1", "-"], True),
            # git apply with whitespace fix only
            (["git", "apply", "--whitespace=fix", "-"], True),
            # git apply strict
            (["git", "apply", "-"], True),
            # patch command as fallback (more lenient)
            (["patch", "-p1", "--fuzz=3", "--ignore-whitespace"], False),
        ]

        last_err = ""
        for cmd, use_check in apply_attempts:
            try:
                if use_check:
                    # Dry run with git apply --check
                    check_cmd = cmd[:-1] + ["--check"] + [cmd[-1]]
                    check = await _run_git(
                        check_cmd, cwd=ctx.workspace_root, stdin=patch_bytes,
                    )
                    if check.returncode != 0:
                        last_err = (check.stderr or check.stdout).strip()
                        continue
                # Real apply
                result = await _run_git(
                    cmd, cwd=ctx.workspace_root, stdin=patch_bytes,
                )
                if result.returncode == 0:
                    modified = await _modified_files(ctx.workspace_root)
                    return ToolResult(
                        success=True,
                        data={"modified_files": modified, "error": None},
                    )
                last_err = (result.stderr or result.stdout).strip()
            except (FileNotFoundError, OSError):
                # Command not found (e.g., patch on Windows), try next
                continue

        # Fallback: Python-based fuzzy patch applier
        try:
            modified = await _python_apply(
                patch_text, ctx.workspace_root, guard,
            )
            if modified:
                return ToolResult(
                    success=True,
                    data={"modified_files": modified, "error": None},
                )
        except Exception as exc:
            last_err = f"python fallback failed: {exc}"

        return ToolResult(
            success=False,
            error=last_err or "patch failed",
            data={"modified_files": []},
        )


class _GitResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


async def _run_git(
    cmd: list[str], cwd: str, stdin: bytes | None = None
) -> _GitResult:
    """Run a git subprocess, returning decoded stdout/stderr."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate(input=stdin)
    return _GitResult(
        returncode=proc.returncode if proc.returncode is not None else 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )


async def _modified_files(workspace_root: str) -> list[str]:
    """Return workspace-relative paths of files changed in the worktree."""
    proc = await asyncio.create_subprocess_exec(
        "git", "diff", "HEAD", "--name-only",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workspace_root,
    )
    stdout, _ = await proc.communicate()
    files = [
        line.strip()
        for line in stdout.decode(errors="replace").splitlines()
        if line.strip()
    ]
    return files


def _extract_paths(patch: str) -> list[str]:
    """Extract target file paths from a unified diff."""
    paths: list[str] = []
    for line in patch.splitlines():
        for prefix in ("+++ ", "--- "):
            if line.startswith(prefix):
                token = line[len(prefix):].split(None, 1)
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


async def _python_apply(
    patch_text: str, workspace_root: str, guard: PathGuard,
) -> list[str]:
    """Python-based fuzzy patch applier.

    Parses unified diff, reads target files, applies changes using
    fuzzy line matching, and writes modified files.
    """
    from difflib import SequenceMatcher

    # Parse the patch into per-file hunks
    files_hunks: dict[str, list[dict]] = {}
    current_file: str | None = None
    current_hunk: dict | None = None

    for line in patch_text.splitlines():
        if line.startswith("--- "):
            token = line[4:].split(None, 1)
            if token:
                p = token[0]
                if p.startswith("a/"):
                    p = p[2:]
                current_file = None if p == "/dev/null" else p
        elif line.startswith("+++ "):
            token = line[4:].split(None, 1)
            if token:
                p = token[0]
                if p.startswith("b/"):
                    p = p[2:]
                if p != "/dev/null":
                    current_file = p
                    files_hunks.setdefault(current_file, [])
        elif line.startswith("@@ ") and current_file:
            # Parse @@ -start,count +start,count @@
            parts = line[3:].split()
            old_info = parts[0] if parts else ""
            if old_info.startswith("-"):
                old_info = old_info[1:]
            try:
                old_start = int(old_info.split(",")[0])
            except ValueError:
                old_start = 1
            current_hunk = {
                "old_start": old_start,
                "lines": [],
            }
            files_hunks[current_file].append(current_hunk)
        elif current_hunk is not None and current_file:
            if line.startswith(" ") or line == "":
                current_hunk["lines"].append((" ", line[1:] if line.startswith(" ") else ""))
            elif line.startswith("-"):
                current_hunk["lines"].append(("-", line[1:]))
            elif line.startswith("+"):
                current_hunk["lines"].append(("+", line[1:]))
            elif line.startswith("\\"):
                pass  # No newline at end marker

    modified_files = []

    for rel_path, hunks in files_hunks.items():
        try:
            validated = guard.validate_path(rel_path)
        except PermissionError:
            continue

        if not validated.is_file():
            continue

        try:
            content = await asyncio.to_thread(
                validated.read_text, encoding="utf-8"
            )
        except Exception:
            continue

        file_lines = content.splitlines(keepends=False)
        result_lines = list(file_lines)

        # Apply hunks in reverse order to preserve line numbers
        for hunk in reversed(hunks):
            old_lines = [item[1] for item in hunk["lines"] if item[0] in (" ", "-")]
            new_lines = [item[1] for item in hunk["lines"] if item[0] in (" ", "+")]

            # Find the best matching position in the file
            best_pos = -1
            best_ratio = 0.0
            search_start = max(0, hunk["old_start"] - 1 - 5)
            search_end = min(len(result_lines), hunk["old_start"] - 1 + 10)

            # Search wider range if needed
            for start in range(
                max(0, search_start),
                min(len(result_lines) - len(old_lines) + 1, search_end + 10),
            ):
                candidate = result_lines[start:start + len(old_lines)]
                ratio = SequenceMatcher(None, old_lines, candidate).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_pos = start

            # Also search from beginning if no good match
            if best_ratio < 0.5:
                for start in range(len(result_lines) - len(old_lines) + 1):
                    candidate = result_lines[start:start + len(old_lines)]
                    ratio = SequenceMatcher(None, old_lines, candidate).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_pos = start

            if best_pos >= 0 and best_ratio > 0.6:
                # Replace old lines with new lines
                result_lines[best_pos:best_pos + len(old_lines)] = new_lines

        new_content = "\n".join(result_lines)
        if content.endswith("\n"):
            new_content += "\n"

        if new_content != content:
            await asyncio.to_thread(
                validated.write_text, new_content, encoding="utf-8"
            )
            modified_files.append(rel_path)

    return modified_files
