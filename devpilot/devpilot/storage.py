"""Atomic single-file persistence; this does not make multiple artifacts a transaction."""

from __future__ import annotations

import os
import uuid
from pathlib import Path


class ArtifactQuotaExceeded(OSError):
    """Admission checks cannot reserve enough room for the next operation."""


def tree_bytes(root: Path) -> int:
    """Count all physical regular files, including logs and Git; never follow links."""
    total = 0
    if root.is_symlink() or root.is_junction():
        raise PermissionError("Linked artifact root")
    if not root.exists():
        return total
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(directory) / name
            if path.is_symlink() or path.is_junction():
                raise PermissionError(f"Linked artifact path: {path}")
        for name in names:
            total += (Path(directory) / name).stat().st_size
    return total


class RunLock:
    """Nonblocking OS lock, released by the kernel after process death."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> RunLock:
        if self.path.is_symlink() or self.path.resolve() != self.path.absolute():
            raise PermissionError("Linked run lock path")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        if self.handle.seek(0, 2) == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            raise RuntimeError("Run is already active in another process") from exc
        return self

    def __exit__(self, *args) -> None:
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
