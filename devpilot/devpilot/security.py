"""Shared file and process policy for trusted local execution, not an OS sandbox."""

from __future__ import annotations

import os
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "runs",
    "workspaces",
}
SENSITIVE_DIRS = {".git", ".ssh", ".aws"}


def forbidden(relative: str) -> bool:
    parts = relative.replace("\\", "/").lower().split("/")
    return (
        any(p in SENSITIVE_DIRS for p in parts)
        or any(".env" in p or "id_rsa" in p or "id_ed25519" in p for p in parts)
        or Path(parts[-1]).suffix in {".pem", ".key", ".p12", ".pfx"}
    )


def linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def permitted_files(root: Path, workspace: Path) -> list[Path]:
    """Enumerate without reading contents or following linked directories."""

    def allowed(path: Path) -> bool:
        if linked(path):
            raise PermissionError(f"Linked path is not permitted: {path.relative_to(workspace)}")
        return not forbidden(path.relative_to(workspace).as_posix())

    if root.is_file():
        return [root] if allowed(root) else []
    result = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        dirs[:] = sorted(d for d in dirs if d.lower() not in SKIP_DIRS and allowed(parent / d))
        for name in sorted(names):
            path = parent / name
            if allowed(path):
                result.append(path)
    return result


def process_environment() -> dict[str, str]:
    """Do not pass model/cloud credentials or user Python hooks to candidate code."""
    names = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "LANG", "LC_ALL"}
    result = {k: v for k, v in os.environ.items() if k.upper() in names}
    result.update(PYTHONUTF8="1", PYTHONNOUSERSITE="1")
    return result


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    for value in secrets:
        if value:
            text = text.replace(value, "[REDACTED]")
    return text
