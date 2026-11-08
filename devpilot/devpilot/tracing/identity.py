"""Logical event identity follows graph node execution across process restarts."""

import hashlib
from contextlib import contextmanager
from contextvars import ContextVar

_scope = ContextVar("trace_identity_scope", default=None)


@contextmanager
def trace_scope(identity):
    token = _scope.set((identity, {}))
    try:
        yield
    finally:
        _scope.reset(token)


def event_identity(event):
    scope = _scope.get()
    if scope is None:
        return None
    identity, counts = scope
    counts[event] = counts.get(event, 0) + 1
    value = f"{identity}:{event}:{counts[event]}"
    return hashlib.sha256(value.encode()).hexdigest()
