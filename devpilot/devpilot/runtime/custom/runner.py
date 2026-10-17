"""Custom runtime runner."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from devpilot.agents.developer import DeveloperAgent
from devpilot.domain.decision import AgentDecision, FinishIntent
from devpilot.domain.result import AgentRunResult
from devpilot.domain.state import DevPilotState, Observation
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.runtime.custom.loop_guard import (
    GuardrailViolation,
    LoopGuard,
    MaxRetriesExceeded,
)
from devpilot.runtime.custom.state_manager import StateManager
from devpilot.security import permitted_files, redact
from devpilot.storage import atomic_write
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.registry import ToolRegistry
from devpilot.tools.repo.file_cache import ReadFileCache
from devpilot.tools.test.failure_parser import parse_test_failures
from devpilot.tracing import MetricsCollector, TraceWriter
from devpilot.verification import TaskVerifier
from devpilot.verification.evidence import capture_snapshot
from devpilot.workspace.sandbox import SandboxWorkspace


class BudgetExceeded(GuardrailViolation):
    """A request or wall-clock limit was exhausted."""


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
        verifier: TaskVerifier | None = None,
        trace_writer: TraceWriter | None = None,
        metrics: MetricsCollector | None = None,
        file_cache: ReadFileCache | None = None,
    ) -> None:
        self.agent = agent
        self.registry = registry
        self.sandbox = sandbox
        self.state_manager = state_manager
        self.context_builder = context_builder
        self.loop_guard = loop_guard
        self.config = config
        self.on_event = on_event
        self.verifier = verifier
        self.trace_writer = trace_writer
        self.metrics = metrics or MetricsCollector()
        self.file_cache = file_cache or ReadFileCache()

    def _emit(self, event_type: str, data: dict) -> None:
        """Emit a progress event to the optional callback."""
        if self.on_event:
            safe = json.loads(redact(json.dumps(data), self.sandbox.secrets))
            self.on_event(event_type, safe)

    def _trace(
        self,
        run_id: str,
        step: int,
        phase: str,
        event: str,
        tool: str | None = None,
        arguments_summary: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Write a trace event if trace_writer is available."""
        if self.trace_writer:
            try:
                self.trace_writer.write_event(
                    run_id, step, phase, event, tool, arguments_summary, data
                )
            except OSError as exc:
                logging.warning("Trace unavailable: %s", type(exc).__name__)

    @staticmethod
    def _enrich_test_failure(tool_result: ToolResult) -> None:
        """Attach structured ``test_failure`` data to a failed test.run result.

        Reads the full pytest output saved to ``test-output.log`` (always
        written by the test.run tool) and parses it into structured data so
        the agent can act on concrete failure details instead of raw text.
        Never raises: on any problem the data is left with a minimal failure
        entry so downstream context building still works.
        """
        if not tool_result.data:
            return
        output = ""
        log_file = tool_result.data.get("log_file")
        if log_file:
            try:
                output = Path(log_file).read_text(encoding="utf-8", errors="replace")
            except OSError:
                output = ""
        try:
            tool_result.data["test_failure"] = parse_test_failures(output)
        except Exception:  # noqa: BLE001 - parser must never break the run
            tool_result.data["test_failure"] = {
                "kind": "test_failure",
                "failed_tests": [],
                "errors": [],
                "summary": "Failed to parse test output",
            }

    async def run(self, task: DevelopmentTask) -> AgentRunResult:
        """Execute the agent loop for a development task."""
        start_time = time.time()
        self.metrics.reset()
        self.loop_guard.reset()
        self.file_cache.clear()
        self.request_count = 0
        self.deadline = None
        self.preparation_ms = 0

        # 1. Initialize state
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        state = self.state_manager.create(task, run_id)
        self.metrics.start_time = start_time
        self._emit(
            "run_started",
            {
                "task_id": task.id,
                "run_id": run_id,
                "phase": state.phase,
                "acceptance_criteria_count": len(task.acceptance_criteria),
            },
        )

        try:
            self._trace(run_id, 0, state.phase, "run_started")
            # 2. Create workspace and freeze trusted evidence before any action.
            workspace_path = self.sandbox.create(run_id)
            trusted = capture_snapshot(
                Path(workspace_path), Path(self.sandbox.get_runs_dir(run_id))
            )
            if self.verifier:
                self.verifier.bind_snapshot(run_id, trusted)

            self.preparation_ms = int((time.time() - start_time) * 1000)
            self._checkpoint(state)
            self.deadline = time.monotonic() + self.config.max_run_seconds
            if self.verifier:
                self.verifier.deadline = self.deadline

            # 3. Main loop
            while state.total_steps < self.config.max_steps:
                self._remaining()
                self._checkpoint(state)
                files = permitted_files(Path(workspace_path), Path(workspace_path))
                if sum(p.stat().st_size for p in files) > self.sandbox.max_bytes:
                    raise GuardrailViolation("workspace_max_bytes")
                self.loop_guard.check_max_steps(state)

                messages = self.context_builder.build(state, workspace_path)
                # Retry LLM call on empty/error responses
                decision = None
                for _attempt in range(3):
                    try:
                        if self.request_count >= self.config.max_llm_requests:
                            raise BudgetExceeded("max_llm_requests")
                        timeout = min(self.config.llm_timeout_seconds, self._remaining())
                        self.request_count += 1
                        decision = await asyncio.wait_for(self.agent.decide(messages), timeout)
                        decision = AgentDecision.model_validate(decision.model_dump())
                        if decision.action:
                            decision.action.tool = self.registry.canonical_name(
                                decision.action.tool
                            )
                        break
                    except BudgetExceeded:
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
                        verification = await self.verifier.verify(
                            task, workspace_path, state, self.registry
                        )
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

                        if verification.success:
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
                            self.state_manager.increment_retry(state)

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

                            failure_obs = Observation(
                                step_id=state.total_steps,
                                source="verifier",
                                name="verification_failed",
                                success=False,
                                summary=(verification.failure_reason or "Verification failed"),
                                data=verification.model_dump(),
                            )
                            self.state_manager.add_observation(state, failure_obs)

                            # Transition back to implementing for repair
                            if state.phase != "implementing":
                                with suppress(ValueError):
                                    self.state_manager.transition_phase(state, "implementing")
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
                            continue
                    else:
                        # No verifier - just complete (backward compat)
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

                # EXECUTE TOOL
                if decision.action:
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
                        deadline=self.deadline,
                    )
                    tool_start = time.time()

                    # Check read_file cache before executing the tool
                    tool_name = decision.action.tool
                    is_read_file = tool_name in (
                        "repo.read_file",
                        "repo_read_file",
                    )
                    cached_result = None
                    if is_read_file:
                        rel_path = decision.action.arguments.get("path", "")
                        full_path = str(Path(workspace_path) / rel_path)
                        cached_result = self.file_cache.get(
                            full_path,
                            decision.action.arguments.get("start_line"),
                            decision.action.arguments.get("end_line"),
                        )

                    if cached_result is not None:
                        tool_result = cached_result
                    else:
                        tool_result = await self.registry.execute(decision.action, ctx)
                        if is_read_file and tool_result.success:
                            self.file_cache.put(
                                full_path,
                                decision.action.arguments.get("start_line"),
                                decision.action.arguments.get("end_line"),
                                tool_result,
                            )

                    tool_duration = int((time.time() - tool_start) * 1000)

                    # Invalidate read_file cache for files modified by
                    # patch/create so subsequent reads get fresh content.
                    if (
                        tool_result.success
                        and tool_result.data
                        and tool_name
                        in (
                            "code.apply_patch",
                            "code_apply_patch",
                            "code.create_file",
                            "code_create_file",
                        )
                    ):
                        for f in tool_result.data.get("modified_files", []):
                            self.file_cache.invalidate(str(Path(workspace_path) / f))

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
                        state.repair_required = True
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
                        state.repair_required = False
                        self.loop_guard.reset_repair_state()

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

        except GuardrailViolation as e:
            if state.phase not in ("completed", "failed"):
                self.state_manager.transition_phase(state, "failed")
            result = self._build_result(state, start_time, None)
            result.error = str(e)
            result.termination_reason = str(e) if isinstance(e, BudgetExceeded) else "guardrail"
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
                data={"reason": str(e)},
            )
            self._trace(
                run_id,
                state.total_steps,
                "failed",
                "guardrail_triggered",
                data={"violation": str(e)},
            )
            return result
        except Exception as e:  # noqa: BLE001 - runner must not crash
            if state.phase not in ("completed", "failed"):
                self.state_manager.transition_phase(state, "failed")
            result = self._build_result(state, start_time, None)
            result.error = f"Unexpected error: {e}"
            result.termination_reason = (
                "run_timeout" if isinstance(e, TimeoutError) else "execution_error"
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
                data={"reason": str(e)},
            )
            return result

    def _remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise BudgetExceeded("max_run_seconds")
        return remaining

    def _maybe_advance_phase(self, state: DevPilotState, decision: AgentDecision) -> None:
        """Auto-advance phase based on tool usage patterns."""
        old_phase = state.phase
        new_phase: str | None = None

        if state.phase == "understanding" and decision.action:
            if decision.action.tool.startswith("repo.") or decision.action.tool.startswith("repo_"):
                new_phase = "exploring"

        elif state.phase == "exploring":
            # Transition to planning if agent provides a plan or enough steps
            if decision.plan_update or state.total_steps >= 10:
                new_phase = "planning"
            # If agent starts using code tools, skip to implementing
            elif decision.action and (
                decision.action.tool.startswith("code.") or decision.action.tool.startswith("code_")
            ):
                new_phase = "implementing"

        elif state.phase == "planning":
            if (
                decision.action
                and (
                    decision.action.tool.startswith("code.")
                    or decision.action.tool.startswith("code_")
                )
            ) or state.total_steps >= 15:
                new_phase = "implementing"

        elif (
            state.phase == "implementing"
            and decision.action
            and (decision.action.tool == "test.run" or decision.action.tool == "test_run")
        ):
            new_phase = "verifying"

        if new_phase is not None:
            self.state_manager.transition_phase(state, new_phase)
            self._emit(
                "phase_changed",
                {
                    "task_id": state.task.id,
                    "from": old_phase,
                    "to": new_phase,
                },
            )

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
            budget={
                "llm_requests": self.request_count,
                "max_llm_requests": self.config.max_llm_requests,
                "max_run_seconds": self.config.max_run_seconds,
                "preparation_ms": self.preparation_ms,
            },
        )

    def _save_artifacts(
        self,
        run_id: str,
        state: DevPilotState,
        result: AgentRunResult,
    ) -> None:
        """Save state.json and result.json to runs directory."""
        if result.error:
            result.error = redact(result.error, self.sandbox.secrets)
        self.metrics.total_steps = state.total_steps
        for path in state.modified_files:
            self.metrics.record_modified_file(path)
        data = json.loads(result.model_dump_json())
        data["metrics"] = self.metrics.to_dict()
        payloads = {
            "state.json": self.state_manager.serialize(state),
            "llm-requests.json": json.dumps(self.metrics.llm_requests, indent=2),
            "result.json": json.dumps(data, indent=2),
        }
        for name, content in payloads.items():
            try:
                self.sandbox.save_artifact(run_id, name, content)
            except OSError as exc:
                result.artifact_errors.append(f"{name}: {type(exc).__name__}")
        if result.artifact_errors:
            recovery = Path(tempfile.gettempdir()) / "devpilot-recovery" / f"{run_id}.json"
            result.recovery_file = str(recovery)
            try:
                atomic_write(
                    recovery,
                    redact(
                        json.dumps(
                            {"result": result.model_dump(), "state": state.model_dump()}, indent=2
                        ),
                        self.sandbox.secrets,
                    ),
                )
            except OSError:
                result.recovery_file = None
                logging.error("Run artifacts and recovery write failed for %s", run_id)

    def _checkpoint(self, state: DevPilotState) -> None:
        try:
            self.sandbox.save_artifact(
                state.run_id, "state.json", self.state_manager.serialize(state)
            )
        except OSError as exc:
            logging.warning("Checkpoint unavailable: %s", type(exc).__name__)
