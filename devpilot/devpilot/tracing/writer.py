"""Tracing event writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devpilot.security import redact
from devpilot.storage import atomic_write
from devpilot.tracing.events import TraceEvent, _now_iso
from devpilot.tracing.identity import event_identity


class TraceWriter:
    """Append trace events to ``runs/{run_id}/trace.jsonl``."""

    def __init__(self, runs_dir: str) -> None:
        self.secrets: tuple[str, ...] = ()
        self.runs_dir = Path(runs_dir)
        self.artifact_store = None

    def write(self, run_id: str, event: TraceEvent) -> None:
        """Append a trace event to ``runs/{run_id}/trace.jsonl``."""
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        trace_path = run_dir / "trace.jsonl"
        line = redact(event.model_dump_json(), self.secrets) + "\n"
        if event.event_id is not None:
            # ID and event share one atomic file commit; no separate dedup index
            # can advance before the event itself becomes durable.
            previous = trace_path.read_text(encoding="utf-8") if trace_path.exists() else ""
            if previous and not previous.endswith("\n"):
                raise OSError("Trace contains an incomplete event")
            for existing in previous.splitlines():
                try:
                    recorded = json.loads(existing)
                except ValueError as exc:
                    raise OSError("Trace contains an incomplete or invalid event") from exc
                if recorded.get("event_id") == event.event_id:
                    return
            content = previous + line
            if self.artifact_store is not None:
                self.artifact_store.save_artifact(run_id, "trace.jsonl", content)
            else:
                atomic_write(trace_path, content)
            return
        if self.artifact_store is not None:
            with (
                self.artifact_store.admit_artifacts(run_id, len(line.encode("utf-8"))),
                trace_path.open("a", encoding="utf-8") as f,
            ):
                f.write(line)
        else:
            with trace_path.open("a", encoding="utf-8") as f:
                f.write(line)

    def write_event(
        self,
        run_id: str,
        step: int,
        phase: str,
        event: str,
        tool: str | None = None,
        arguments_summary: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Convenience method to create and write a TraceEvent."""
        trace_event = TraceEvent(
            run_id=run_id,
            step=step,
            phase=phase,
            event=event,
            tool=tool,
            arguments_summary=arguments_summary,
            timestamp=_now_iso(),
            data=data,
            event_id=event_identity(event),
        )
        self.write(run_id, trace_event)
