"""Custom runtime runner."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from devpilot.agents.developer import DeveloperAgent
from devpilot.domain.decision import AgentDecision, FinishIntent
from devpilot.domain.result import AgentRunResult
from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.runtime.custom.loop_guard import GuardrailViolation, LoopGuard
from devpilot.runtime.custom.state_manager import StateManager
from devpilot.tools.context import ToolContext
from devpilot.tools.registry import ToolRegistry
from devpilot.workspace.sandbox import SandboxWorkspace


class CustomAgentRunner:
    """Orchestrates the agent loop: context -> decision -> tool -> guard."""

    def __init__(
        self,
        agent: DeveloperAgent,
        registry: ToolRegistry,
        sandbox: SandboxWorkspace,
        state_manager: StateManager,
        context_builder: ContextBuilder,
        loop_guard: LoopGuard,
        config: RuntimeConfig,
        on_event: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.agent = agent
        self.registry = registry
        self.sandbox = sandbox
        self.state_manager = state_manager
        self.context_builder = context_builder
        self.loop_guard = loop_guard
        self.config = config
        self.on_event = on_event

    def _emit(self, event_type: str, data: dict) -> None:
        """Emit a progress event to the optional callback."""
        if self.on_event:
            self.on_event(event_type, data)

    async def run(self, task: DevelopmentTask) -> AgentRunResult:
        """Execute the agent loop for a development task."""
        start_time = time.time()

        # 1. Initialize state
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        state = self.state_manager.create(task, run_id)
        self._emit("run_started", {
            "task_id": task.id,
            "run_id": run_id,
            "phase": state.phase,
            "acceptance_criteria_count": len(task.acceptance_criteria),
        })

        # 2. Create workspace
        workspace_path = self.sandbox.create(run_id)

        try:
            # 3. Main loop
            while state.total_steps < self.config.max_steps:
                self.loop_guard.check_max_steps(state)

                messages = self.context_builder.build(state, workspace_path)
                decision = await self.agent.decide(messages)
                self._emit("agent_decision", {
                    "task_id": task.id,
                    "phase": state.phase,
                    "decision_type": (
                        "finish" if decision.finish
                        else "action" if decision.action
                        else "plan_update"
                    ),
                })

                if decision.finish:
                    self.state_manager.request_completion(state)
                    old_phase = state.phase
                    self.state_manager.transition_phase(state, "completed")
                    self._emit("phase_changed", {
                        "task_id": task.id,
                        "from": old_phase,
                        "to": "completed",
                    })
                    result = self._build_result(
                        state, start_time, decision.finish
                    )
                    self._save_artifacts(run_id, state, result)
                    self._emit("run_completed", {
                        "task_id": task.id,
                        "run_id": run_id,
                        "status": result.status,
                        "summary": result.summary,
                        "total_steps": result.total_steps,
                    })
                    return result

                if decision.action:
                    self._emit("tool_called", {
                        "task_id": task.id,
                        "phase": state.phase,
                        "tool": decision.action.tool,
                        "arguments": decision.action.arguments,
                    })
                    ctx = ToolContext(
                        workspace_root=workspace_path, run_id=run_id
                    )
                    tool_start = time.time()
                    tool_result = await self.registry.execute(
                        decision.action, ctx
                    )
                    tool_duration = int(
                        (time.time() - tool_start) * 1000
                    )

                    self.state_manager.apply_tool_result(
                        state, tool_result, decision.action.tool, tool_duration
                    )
                    self._maybe_advance_phase(state, decision)
                    self._emit("tool_result", {
                        "task_id": task.id,
                        "phase": state.phase,
                        "tool": decision.action.tool,
                        "success": tool_result.success,
                        "summary": (
                            "OK" if tool_result.success
                            else (tool_result.error or "failed")
                        ),
                        "data": tool_result.data,
                    })
                    self.loop_guard.inspect(state, decision, tool_result)

                if decision.plan_update:
                    state.plan = decision.plan_update

            # Exceeded max steps
            self.state_manager.transition_phase(state, "failed")
            result = self._build_result(state, start_time, None)
            result.error = f"Max steps ({self.config.max_steps}) exceeded"
            self._save_artifacts(run_id, state, result)
            self._emit("run_failed", {
                "task_id": task.id,
                "run_id": run_id,
                "error": result.error,
            })
            return result

        except GuardrailViolation as e:
            if state.phase not in ("completed", "failed"):
                self.state_manager.transition_phase(state, "failed")
            result = self._build_result(state, start_time, None)
            result.error = str(e)
            self._save_artifacts(run_id, state, result)
            self._emit("run_failed", {
                "task_id": task.id,
                "run_id": run_id,
                "error": result.error,
            })
            return result
        except Exception as e:  # noqa: BLE001 - runner must not crash
            if state.phase not in ("completed", "failed"):
                self.state_manager.transition_phase(state, "failed")
            result = self._build_result(state, start_time, None)
            result.error = f"Unexpected error: {e}"
            self._save_artifacts(run_id, state, result)
            self._emit("run_failed", {
                "task_id": task.id,
                "run_id": run_id,
                "error": result.error,
            })
            return result

    def _maybe_advance_phase(
        self, state: DevPilotState, decision: AgentDecision
    ) -> None:
        """Auto-advance phase based on tool usage patterns."""
        old_phase = state.phase
        new_phase: str | None = None
        if state.phase == "understanding" and decision.action:
            if decision.action.tool.startswith("repo."):
                new_phase = "exploring"
        elif state.phase == "exploring" and decision.plan_update:
            new_phase = "planning"
        elif state.phase == "planning" and decision.action:
            if decision.action.tool.startswith("code."):
                new_phase = "implementing"
        elif (
            state.phase == "implementing"
            and decision.action
            and decision.action.tool == "test.run"
        ):
            new_phase = "verifying"

        if new_phase is not None:
            self.state_manager.transition_phase(state, new_phase)
            self._emit("phase_changed", {
                "task_id": state.task.id,
                "from": old_phase,
                "to": new_phase,
            })

    def _build_result(
        self,
        state: DevPilotState,
        start_time: float,
        finish_intent: FinishIntent | None,
    ) -> AgentRunResult:
        """Build AgentRunResult from final state."""
        duration_ms = int((time.time() - start_time) * 1000)
        return AgentRunResult(
            run_id=state.run_id,
            task_id=state.task.id,
            status="completed" if state.phase == "completed" else "failed",
            phase=state.phase,
            total_steps=state.total_steps,
            modified_files=state.modified_files,
            observations=state.observations,
            summary=finish_intent.summary if finish_intent else None,
            risk=finish_intent.risk if finish_intent else None,
            duration_ms=duration_ms,
            error=None if state.phase == "completed" else state.phase,
        )

    def _save_artifacts(
        self,
        run_id: str,
        state: DevPilotState,
        result: AgentRunResult,
    ) -> None:
        """Save state.json and result.json to runs directory."""
        self.sandbox.save_artifact(
            run_id, "state.json", self.state_manager.serialize(state)
        )
        self.sandbox.save_artifact(
            run_id, "result.json", result.model_dump_json(indent=2)
        )
