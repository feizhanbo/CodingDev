"""State manager for the custom runtime."""

from __future__ import annotations

import uuid

from devpilot.domain.state import DevPilotState, Observation, TestRun
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.context import ToolResult

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "understanding": {"exploring", "completed", "failed"},
    "exploring": {"planning", "implementing", "exploring", "completed", "failed"},
    "planning": {"implementing", "completed", "failed"},
    "implementing": {"verifying", "completed", "failed"},
    "verifying": {"completed", "implementing", "planning", "failed"},
    "completed": set(),
    "failed": set(),
}


class StateManager:
    """Manages DevPilotState lifecycle: creation, transitions, serialization."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def create(self, task: DevelopmentTask, run_id: str | None = None) -> DevPilotState:
        """Initialize new DevPilotState for a task."""
        rid = run_id if run_id is not None else f"run_{uuid.uuid4().hex[:8]}"
        return DevPilotState(
            run_id=rid,
            task=task,
            phase="understanding",
        )

    def transition_phase(self, state: DevPilotState, new_phase: str) -> None:
        """Transition state phase. Validate allowed transitions."""
        allowed = _ALLOWED_TRANSITIONS.get(state.phase, set())
        if new_phase not in allowed:
            raise ValueError(f"Invalid phase transition: {state.phase} -> {new_phase}")
        state.phase = new_phase  # type: ignore[assignment]

    def add_observation(self, state: DevPilotState, obs: Observation) -> None:
        """Add an observation to state."""
        state.observations.append(obs)
        state.current_step += 1
        state.total_steps += 1

    def apply_tool_result(
        self,
        state: DevPilotState,
        tool_result: ToolResult,
        tool_name: str,
        duration_ms: int,
    ) -> None:
        """Apply tool execution result to state."""
        summary = "OK" if tool_result.success else (tool_result.error or "failed")
        obs = Observation(
            step_id=state.total_steps + 1,
            source="tool",
            name=tool_name,
            success=tool_result.success,
            summary=summary,
            data=tool_result.data,
            duration_ms=duration_ms,
        )
        if tool_result.data and "modified_files" in tool_result.data:
            for f in tool_result.data["modified_files"]:
                if f not in state.modified_files:
                    state.modified_files.append(f)
        if tool_name == "test.run" and tool_result.data:
            data = tool_result.data
            state.test_runs.append(
                TestRun(
                    run_id=state.run_id,
                    exit_code=data.get("exit_code", 0 if tool_result.success else -1),
                    passed=data.get("passed"),
                    failed=data.get("failed"),
                    duration_ms=duration_ms,
                    summary=str(data.get("summary", summary)),
                    log_file=data.get("log_file"),
                )
            )
        self.add_observation(state, obs)

    def request_completion(self, state: DevPilotState) -> None:
        """Mark that agent requested finish."""
        state.completion_requested = True

    def reject_verification(self, state: DevPilotState, report: dict) -> None:
        state.retry_count += 1
        state.completion_requested = False
        self.set_repair(state, "verification", True)
        state.verification_report = report
        self.add_observation(state, Observation(
            step_id=state.total_steps + 1, source="verifier",
            name="verification_failed", success=False,
            summary=report.get("failure_reason") or "Verification failed", data=report,
        ))
        if state.phase in {"completed", "failed"}:
            raise ValueError("Cannot repair a terminal run")
        state.phase = "implementing"

    def set_repair(self, state: DevPilotState, source: str, required: bool) -> None:
        sources = set(state.repair_sources)
        if required:
            sources.add(source)
        else:
            sources.discard(source)
        state.repair_sources = sorted(sources)
        state.repair_required = bool(sources)

    def increment_retry(self, state: DevPilotState) -> None:
        """Increment retry count."""
        state.retry_count += 1

    def serialize(self, state: DevPilotState) -> str:
        """Serialize state to JSON."""
        return state.model_dump_json(indent=2)

    def deserialize(self, json_str: str) -> DevPilotState:
        """Deserialize state from JSON."""
        return DevPilotState.model_validate_json(json_str)
