"""Reusable execution steps; orchestration is supplied by each runtime."""

import logging
import time

from devpilot.domain.state import Observation
from devpilot.llm.base import ContextBudgetExceeded
from devpilot.runtime.shared.loop_guard import GuardrailViolation, MaxRetriesExceeded
from devpilot.storage import tree_bytes
from devpilot.tools.context import ToolContext


class BudgetExceeded(GuardrailViolation):
    """A request or wall-clock limit was exhausted."""


class ExecutionSteps:
    async def _verify_candidate(self, state, workspace_path):
        return await self.acceptance.verify(
            self.verifier, state.task, workspace_path, state,
            self.registry, self.budget_service,
        )

    def _begin_model_request(self, state, messages):
        """Runtime-specific durable admission; failures must not trigger a retry."""

    def _end_model_request(self, state, decision):
        """Runtime-specific receipt after local request accounting."""

    async def decide_step(self, state, messages):
        run_id = state.run_id
        # Retry LLM call on empty/error responses
        decision = None
        if self.attempts_in_turn >= 3:
            raise BudgetExceeded("interrupted_model_retries_exhausted")
        for _attempt in range(self.attempts_in_turn, 3):
            if self.request_count >= self.config.max_llm_requests:
                raise BudgetExceeded("max_llm_requests")
            self._remaining()
            self.request_count += 1
            self.attempts_in_turn = _attempt + 1
            self.agent.last_request = None
            self._begin_model_request(state, messages)
            self._checkpoint(state, "llm_inflight")
            try:
                timeout = min(self.config.llm_timeout_seconds, self._remaining())
                decision = await self.decisions.decide(
                    self.agent, self.registry, messages, timeout
                )
                break
            except (BudgetExceeded, ContextBudgetExceeded):
                raise
            except Exception as exc:
                if _attempt == 2:
                    raise

                logging.warning(
                    "LLM call attempt %d failed: %s, retrying...",
                    _attempt + 1,
                    type(exc).__name__,
                )
                continue
            finally:
                if self.agent.last_request is not None:
                    request = self.agent.last_request.model_dump()
                    request.update(attempt=_attempt + 1, step=state.total_steps)
                    self.metrics.record_llm_request(request)
                    self._trace(
                        run_id,
                        state.total_steps,
                        state.phase,
                        "llm_request",
                        data=request,
                    )
                self._end_model_request(state, decision)
        return decision

    async def execute_tool_step(self, state, decision, workspace_path, trusted):
        run_id = state.run_id
        task = state.task
        self._emit(
            "tool_called",
            {
                "task_id": task.id,
                "phase": state.phase,
                "tool": decision.action.tool,
                "arguments": decision.action.arguments,
            },
        )
        self._trace(
            run_id,
            state.total_steps,
            state.phase,
            "tool_call",
            tool=decision.action.tool,
            arguments_summary=str(decision.action.arguments),
        )
        ctx = ToolContext(
            workspace_root=workspace_path,
            run_id=run_id,
            artifacts_dir=self.sandbox.get_runs_dir(run_id),
            trusted_root=str(trusted),
            test_timeout_seconds=min(
                self.config.test_timeout_seconds, self._remaining()
            ),
            deadline=min(
                self.deadline, time.monotonic() + self.config.tool_timeout_seconds
            ),
            max_output_bytes=self.config.max_tool_output_bytes,
        )
        tool_start = time.time()

        tool_name = decision.action.tool
        if tool_name == "test.run":
            self.sandbox.check_artifacts(run_id, self.config.max_test_output_bytes)
        self._checkpoint(state, "tool_inflight")
        with self.sandbox.admit_workspace(run_id), self.sandbox.admit_artifacts(run_id):
            tool_result = await self.tools.execute(
                self.registry,
                decision.action,
                ctx,
                min(self.config.tool_timeout_seconds, self._remaining()),
            )
        self._remaining()
        tool_duration = int((time.time() - tool_start) * 1000)

        return tool_result, tool_duration

    def plan_feedback_step(self, state, decision, plan_update_feedback):
        run_id = state.run_id
        # Handle plan update
        if decision.plan_update:
            if state.plan is None:
                self._trace(
                    run_id,
                    state.total_steps,
                    state.phase,
                    "plan_created",
                )
            else:
                self._trace(
                    run_id,
                    state.total_steps,
                    state.phase,
                    "plan_updated",
                )
            state.plan = decision.plan_update

            # If only plan_update (no action), still increment step
            # and try to advance phase
            if not decision.action:
                obs = Observation(
                    step_id=state.total_steps + 1,
                    source="runtime",
                    name="plan_update",
                    success=True,
                    summary=f"Plan updated (revision {state.plan.revision})",
                )
                self.state_manager.add_observation(state, obs)
                self._maybe_advance_phase(state, decision)

        # Inject runtime feedback as the last observation so the
        # ContextBuilder surfaces it as RUNTIME FEEDBACK on the next
        # iteration. Placed after plan_update handling so the feedback
        # is observations[-1] (highest recency / not buried).
        if plan_update_feedback:
            feedback_obs = Observation(
                step_id=state.total_steps + 1,
                source="runtime",
                name="guardrail_feedback",
                success=False,
                summary=plan_update_feedback.get(
                    "message",
                    plan_update_feedback.get("reason", "Guard feedback"),
                ),
                data=plan_update_feedback,
            )
            self.state_manager.add_observation(state, feedback_obs)


    def observe_step(self, state, decision, tool_result, tool_duration, start_time):
        run_id = state.run_id
        task = state.task
        # Enrich failed test.run output with structured failure
        # data before the observation is recorded.
        if decision.action.tool == "test.run" and not tool_result.success:
            self._enrich_test_failure(tool_result)

        self.state_manager.apply_tool_result(
            state, tool_result, decision.action.tool, tool_duration
        )
        self._maybe_advance_phase(state, decision)
        self.metrics.record_tool_call(tool_result.success)
        if tool_result.data and "modified_files" in tool_result.data:
            for f in tool_result.data["modified_files"]:
                self.metrics.record_modified_file(f)
        self._emit(
            "tool_result",
            {
                "task_id": task.id,
                "phase": state.phase,
                "tool": decision.action.tool,
                "success": tool_result.success,
                "summary": (
                    "OK" if tool_result.success else (tool_result.error or "failed")
                ),
                "data": tool_result.data,
            },
        )
        self._trace(
            run_id,
            state.total_steps,
            state.phase,
            "tool_result",
            tool=decision.action.tool,
            data={
                "success": tool_result.success,
                "summary": (
                    "OK" if tool_result.success else (tool_result.error or "failed")
                ),
            },
        )
        self.loop_guard.inspect(state, decision, tool_result)

        # Check if test.run failed - increment retry
        if decision.action.tool == "test.run" and not tool_result.success:
            self.metrics.record_test_retry()
            self.state_manager.increment_retry(state)
            self.state_manager.set_repair(state, "test", True)
            try:
                self.loop_guard.check_test_retries(state)
            except MaxRetriesExceeded:
                self.state_manager.transition_phase(state, "failed")
                result = self._build_result(state, start_time, None)
                result.error = "Max retries exceeded"
                self._save_artifacts(run_id, state, result)
                self._emit(
                    "run_failed",
                    {
                        "task_id": task.id,
                        "run_id": run_id,
                        "error": result.error,
                    },
                )
                self._trace(
                    run_id,
                    state.total_steps,
                    "failed",
                    "run_failed",
                    data={"reason": "max_retries"},
                )
                return result
        elif decision.action.tool == "test.run" and tool_result.success:
            self.state_manager.set_repair(state, "test", False)
            self.loop_guard.reset_repair_state()

        return None

    async def verify_step(self, state, decision, workspace_path, trusted, files, start_time):
        run_id = state.run_id
        task = state.task
        self.state_manager.request_completion(state)

        # Run verifier if available
        if self.verifier:
            self._emit(
                "verifier_started",
                {
                    "task_id": task.id,
                    "phase": state.phase,
                },
            )
            self._trace(
                run_id,
                state.total_steps,
                state.phase,
                "verifier_started",
            )
            self.sandbox.check_artifacts(
                run_id,
                2 * tree_bytes(trusted / "baseline")
                + 3 * sum(p.stat().st_size for p in files)
                + 2 * self.config.max_test_output_bytes,
            )
            self._checkpoint(state, "verifier_inflight")
            self._remaining()
            with self.sandbox.admit_artifacts(run_id):
                verification = await self._verify_candidate(state, workspace_path)
            self._remaining()
            self._emit(
                "verifier_result",
                {
                    "task_id": task.id,
                    "success": verification.success,
                    "failure_reason": verification.failure_reason,
                },
            )
            self._trace(
                run_id,
                state.total_steps,
                state.phase,
                "verifier_result",
                data=verification.model_dump(),
            )

            state.verification_report = verification.model_dump()
            if verification.success:
                self.state_manager.set_repair(state, "verification", False)
                self.state_manager.set_repair(state, "test", False)
                # COMPLETED - verifier passed
                old_phase = state.phase
                self.state_manager.transition_phase(state, "completed")
                self._emit(
                    "phase_changed",
                    {
                        "task_id": task.id,
                        "from": old_phase,
                        "to": "completed",
                    },
                )
                result = self._build_result(state, start_time, decision.finish)
                self._save_artifacts(run_id, state, result)
                self._emit(
                    "run_completed",
                    {
                        "task_id": task.id,
                        "run_id": run_id,
                        "status": result.status,
                        "summary": result.summary,
                        "total_steps": result.total_steps,
                    },
                )
                self._trace(
                    run_id,
                    state.total_steps,
                    "completed",
                    "run_completed",
                )
                return result
            else:
                # VERIFIER REJECTED - feed failure back to agent
                self.metrics.record_finish_rejected()
                self.state_manager.reject_verification(state, verification.model_dump())

                # Check max retries on verifier rejection
                if state.retry_count >= self.config.max_test_retries:
                    self.state_manager.transition_phase(state, "failed")
                    result = self._build_result(state, start_time, None)
                    result.error = (
                        f"Max retries ({self.config.max_test_retries})"
                        " exceeded after verifier rejection"
                    )
                    self._save_artifacts(run_id, state, result)
                    self._emit(
                        "run_failed",
                        {
                            "task_id": task.id,
                            "run_id": run_id,
                            "error": result.error,
                        },
                    )
                    self._trace(
                        run_id,
                        state.total_steps,
                        "failed",
                        "run_failed",
                        data={"reason": result.error},
                    )
                    return result

                self._trace(
                    run_id,
                    state.total_steps,
                    state.phase,
                    "state_transition",
                    data={
                        "reason": "verification_failed",
                        "failure": verification.failure_reason,
                    },
                )
                self.attempts_in_turn = 0
                return None
        return None

    def max_steps_step(self, state, start_time):
        run_id = state.run_id
        task = state.task
        # Exceeded max steps
        self.state_manager.transition_phase(state, "failed")
        result = self._build_result(state, start_time, None)
        result.error = f"Max steps ({self.config.max_steps}) exceeded"
        self._save_artifacts(run_id, state, result)
        self._emit(
            "run_failed",
            {
                "task_id": task.id,
                "run_id": run_id,
                "error": result.error,
            },
        )
        self._trace(run_id, state.total_steps, "failed", "run_failed")
        return result


