"""Evaluation metrics collection."""

from __future__ import annotations

from devpilot.domain.result import AgentRunResult
from devpilot.domain.state import DevPilotState


def collect_metrics(run_result: AgentRunResult, state: DevPilotState) -> dict:
    """Collect metrics from a run result and state.

    Returns a dict with keys: total_steps, tool_calls, tool_failures,
    test_retries, modified_files, duration_ms.
    """
    tool_calls = sum(1 for o in run_result.observations if o.source == "tool")
    tool_failures = sum(
        1 for o in run_result.observations
        if o.source == "tool" and not o.success
    )
    return {
        "total_steps": run_result.total_steps,
        "tool_calls": tool_calls,
        "tool_failures": tool_failures,
        "test_retries": state.retry_count,
        "modified_files": len(run_result.modified_files),
        "duration_ms": run_result.duration_ms or 0,
    }
