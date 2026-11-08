"""Cooperative local I/O limits, independent of any agent runtime."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ExecutionPolicy:
    deadline: float | None = None
    output_limit: int = 2097152
    cancel: threading.Event | None = None
    timeout_reason: str = "run_timeout"


current_policy: ContextVar[ExecutionPolicy] = ContextVar(
    "execution_policy",
    default=ExecutionPolicy(),  # noqa: B039 - frozen immutable default
)


def check_execution() -> None:
    policy = current_policy.get()
    if policy.cancel is not None and policy.cancel.is_set():
        raise TimeoutError("operation_cancelled")
    if policy.deadline is not None and time.monotonic() >= policy.deadline:
        raise TimeoutError(policy.timeout_reason)


def remaining(default: float = 120) -> float:
    check_execution()
    deadline = current_policy.get().deadline
    return min(default, deadline - time.monotonic()) if deadline is not None else default


@contextmanager
def execution_scope(**changes):
    policy = current_policy.get()
    if changes.get("deadline") is None:
        changes.pop("deadline", None)
    if changes.get("deadline") is not None and policy.deadline is not None:
        changes["deadline"] = min(changes["deadline"], policy.deadline)
    token = current_policy.set(replace(policy, **changes))
    try:
        check_execution()
        yield current_policy.get()
    finally:
        current_policy.reset(token)


def copy_file(source, target):
    """Copy in bounded chunks; cancellation finishes before the caller returns."""
    with open(source, "rb") as reader, open(target, "wb") as writer:
        while chunk := reader.read(65536):
            check_execution()
            writer.write(chunk)
    return target
