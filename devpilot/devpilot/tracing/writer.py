"""Tracing event writer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from devpilot.tracing.events import TraceEvent, _now_iso


class TraceWriter:
    """Append trace events to ``runs/{run_id}/trace.jsonl``."""

    def __init__(self, runs_dir: str) -> None:
        self.runs_dir = Path(runs_dir)

    def write(self, run_id: str, event: TraceEvent) -> None:
        """Append a trace event to ``runs/{run_id}/trace.jsonl``."""
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        trace_path = run_dir / "trace.jsonl"
        line = event.model_dump_json() + "\n"
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
        )
        self.write(run_id, trace_event)
