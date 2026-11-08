"""Custom serial loop on the shared run lifecycle."""
import tempfile as tempfile
import uuid as uuid
from pathlib import Path

from devpilot.runtime.shared.lifecycle import RuntimeLifecycle
from devpilot.runtime.shared.loop_guard import GuardrailViolation
from devpilot.runtime.shared.steps import BudgetExceeded as BudgetExceeded
from devpilot.security import permitted_files
from devpilot.storage import tree_bytes


class CustomAgentRunner(RuntimeLifecycle):
    runtime_kind = "custom"

    async def _execute_loop(self, state, workspace_path, trusted, start_time):
        run_id = state.run_id
        task = state.task
        # 3. Main loop
        while state.total_steps < self.config.max_steps:
            self._remaining()
            self._checkpoint(state)
            self.sandbox.check_artifacts(run_id)
            files = permitted_files(Path(workspace_path), Path(workspace_path))
            if tree_bytes(Path(workspace_path)) > self.sandbox.max_bytes:
                raise GuardrailViolation("workspace_max_bytes")
            self.loop_guard.check_max_steps(state)

            messages = self.context_builder.build(state, workspace_path)
            decision = await self.decide_step(state, messages)
            decision_type = (
                "finish" if decision.finish else "action" if decision.action else "plan_update"
            )
            self._emit(
                "agent_decision",
                {
                    "task_id": task.id,
                    "phase": state.phase,
                    "decision_type": decision_type,
                },
            )
            self._trace(
                run_id,
                state.total_steps,
                state.phase,
                "agent_decision",
                data={"decision_type": decision_type},
            )

            # Check for plan_update loop (soft warning + hard stop).
            # The call mutates guard state and may raise GuardrailViolation,
            # which is handled by the existing except block below.
            plan_update_feedback = self.loop_guard.check_plan_update_loop(
                decision, state.phase, state.repair_required
            )
            if plan_update_feedback:
                self._trace(
                    run_id,
                    state.total_steps,
                    state.phase,
                    "guardrail_triggered",
                    data=plan_update_feedback,
                )

            # CHECK FOR FINISH
            if decision.finish:
                terminal = await self.verify_step(
                    state, decision, workspace_path, trusted, files, start_time
                )
                if terminal is not None:
                    return terminal
                continue
            # EXECUTE TOOL
            if decision.action:
                tool_result, tool_duration = await self.execute_tool_step(
                    state, decision, workspace_path, trusted
                )

                terminal = self.observe_step(
                    state, decision, tool_result, tool_duration, start_time
                )
                if terminal is not None:
                    return terminal

            self.plan_feedback_step(state, decision, plan_update_feedback)

            self.attempts_in_turn = 0
            self._checkpoint(state)

        return self.max_steps_step(state, start_time)
