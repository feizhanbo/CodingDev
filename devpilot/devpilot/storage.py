"""Atomic single-file persistence; this does not make multiple artifacts a transaction."""

from __future__ import annotations

import json
import os
import uuid
from contextvars import ContextVar
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
            try:
                total += (Path(directory) / name).stat().st_size
            except FileNotFoundError:
                # Git/pytest may remove a transient file during a live capacity scan.
                # Admission also checks again after the owned process has exited.
                continue
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


active_capacity: ContextVar = ContextVar("active_capacity", default=None)


class CapacityReservation:
    """Serialize capacity admission across processes and reconcile stale reservations.

    The kernel lock is authoritative. A journal surviving process death is reclaimed
    only after physical files have been counted under that lock. This is cooperative
    admission control, not a hard disk sandbox for arbitrary candidate code.
    """

    def __init__(self, root, directory, total_limit, run_limit, reserve=0):
        self.root, self.directory = Path(root), Path(directory)
        self.total_limit, self.run_limit = total_limit, run_limit
        self.reserve = reserve
        self.lock = RunLock(self.root / ".capacity.lock")
        self.journal = self.root / ".capacity-reservation.json"
        self.token = None
        self.nested = False
        self.parent = None

    def check(self, extra=0):
        if self.parent is not None:
            self.parent.check()
        if tree_bytes(self.directory) + extra > self.run_limit:
            raise ArtifactQuotaExceeded("run_capacity_exceeded")
        if tree_bytes(self.root) + extra > self.total_limit:
            raise ArtifactQuotaExceeded("shared_capacity_exceeded")

    def __enter__(self):
        active = active_capacity.get()
        if active is not None and active.root == self.root:
            active.check(self.reserve)
            self.nested = True
            return active
        self.parent = active
        try:
            self.lock.__enter__()
        except RuntimeError as exc:
            raise ArtifactQuotaExceeded("shared_capacity_busy; retry admission later") from exc
        try:
            # Reconcile actual files before reclaiming any stale reservation.
            self.check(self.reserve + 512)
            atomic_write(
                self.journal,
                json.dumps(
                    {"pid": os.getpid(), "directory": str(self.directory), "bytes": self.reserve}
                ),
            )
            self.token = active_capacity.set(self)
            return self
        except BaseException:
            self.lock.__exit__()
            raise

    def __exit__(self, exc_type, exc, tb):
        if self.nested:
            return
        try:
            if exc_type is None:
                self.check()
        finally:
            if self.token is not None:
                active_capacity.reset(self.token)
            try:
                # Remove only our bookkeeping record, never run evidence.
                self.journal.unlink(missing_ok=True)
            finally:
                self.lock.__exit__()


def check_active_capacity():
    active = active_capacity.get()
    if active is not None:
        active.check()
