"""Tracing event definitions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel


class TraceEvent(BaseModel):
    """A single trace event recorded during an agent run.

    Events are appended to ``runs/{run_id}/trace.jsonl`` as JSON lines.
    """

    run_id: str
    step: int
    phase: str
    event: str
    tool: str | None = None
    arguments_summary: str | None = None
    timestamp: str | None = None
    data: dict[str, Any] | None = None


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()
