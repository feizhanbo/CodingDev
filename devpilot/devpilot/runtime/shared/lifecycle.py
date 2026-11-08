"""Custom runtime runner."""

from __future__ import annotations

import json
import logging
import tempfile
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any

from devpilot.agents.developer import DeveloperAgent
from devpilot.domain.decision import AgentDecision, FinishIntent
from devpilot.domain.result import AgentRunResult
from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.execution import execution_scope
from devpilot.llm.base import ContextBudgetExceeded
from devpilot.processes import run_sync
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.budget import RunBudget
from devpilot.runtime.contracts import RunOutcome
from devpilot.runtime.manifest import manifest_for, validate_manifest
from devpilot.runtime.shared.context import ContextBuilder
from devpilot.runtime.shared.loop_guard import (
    GuardrailViolation,
    LoopGuard,
)
from devpilot.runtime.shared.recovery import (
    Checkpoint,
    recovery_inventory,
    restore_fields,
    runtime_identity,
    validate_run_id,
)
from devpilot.runtime.shared.services import (
    AcceptanceService,
    DecisionService,
    ToolExecutionService,
)
from devpilot.runtime.shared.session import RunSession
from devpilot.runtime.shared.state_manager import StateManager
from devpilot.runtime.shared.steps import BudgetExceeded, ExecutionSteps
from devpilot.security import permitted_files, redact
from devpilot.storage import ArtifactQuotaExceeded, RunLock, atomic_write, tree_bytes
from devpilot.tools.context import ToolResult
from devpilot.tools.registry import ToolRegistry
from devpilot.tools.repo.file_cache import ReadFileCache
from devpilot.tools.test.failure_parser import parse_test_failures
from devpilot.tracing import MetricsCollector, TraceWriter
from devpilot.verification import TaskVerifier
from devpilot.verification.evidence import capture_snapshot
from devpilot.workspace.sandbox import SandboxWorkspace


class RuntimeLifecycle(ExecutionSteps):
    """Orchestrates the agent loop: context -> decision -> tool -> guard."""

    runtime_kind = "custom"

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
        if verifier is None:
            raise ValueError("A verifier is required for every run")
        self.agent = agent
        self.registry = registry
        self.sandbox = sandbox
        self.state_manager = state_manager
        self.context_builder = context_builder
        self.context_builder.reserved_chars = len(getattr(agent.llm_client, "_SCHEMA_HINT", ""))
        self.loop_guard = loop_guard
        self.config = config
        self.on_event = on_event
        self.verifier = verifier
        self.trace_writer = trace_writer
        self.metrics = metrics or MetricsCollector()
        self.file_cache = file_cache or ReadFileCache()
        self.sandbox.diagnostic_reserve_bytes = config.diagnostic_reserve_bytes
        if trace_writer:
            trace_writer.artifact_store = sandbox
        self.purpose = "ordinary"
        self.decisions = DecisionService()
        self.tools = ToolExecutionService()
        self.acceptance = AcceptanceService()

    def _emit(self, event_type: str, data: dict) -> None:
        """Emit a progress event to the optional callback."""
        if self.on_event:
            safe = json.loads(redact(json.dumps(data), self.sandbox.secrets))
            try:
                self.on_event(event_type, safe)
            except Exception as exc:  # noqa: BLE001 - display errors must not lose artifacts
                logging.warning("Progress callback failed: %s", type(exc).__name__)

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
                self._trace_failure = exc
                terminal = getattr(self, "_terminal_result", None)
                if terminal is not None:
                    terminal.artifact_errors.append(f"trace.jsonl: {type(exc).__name__}")
                    terminal.status = "failed"
                    terminal.phase = "failed"
                    terminal.termination_reason = (
                        terminal.termination_reason or "persistence_failed"
                    )
                    with suppress(OSError):
                        self.sandbox.save_artifact(
                            run_id, "result.json", terminal.model_dump_json()
                        )
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

    def _outcome(self, result):
        directory = Path(self.sandbox.get_runs_dir(result.run_id))
        state_file = directory / "state.json"
        state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
        diff_file = directory / "final.diff"
        diff = diff_file.read_text(encoding="utf-8") if diff_file.exists() else ""
        return RunOutcome(
            result=result,
            workspace=self.sandbox.get_repo_path(result.run_id),
            artifacts=str(directory),
            evidence=dict(self.verifier.last_results.get(result.run_id, {})),
            statistics=self.metrics.to_dict(),
            budget=self.budget_service.snapshot(),
            state=state,
            final_diff=diff,
        )


    async def run_outcome(self, task: DevelopmentTask) -> RunOutcome:
        """Public result projection owned by the runtime implementation."""
        return self._outcome(await self.run(task))

    async def resume_outcome(self, run_id: str) -> RunOutcome:
        return self._outcome(await self.resume(run_id))

    async def run(self, task: DevelopmentTask) -> AgentRunResult:
        """Execute a new run under an OS lock that also protects resume."""
        while True:
            run_id = f"run_{uuid.uuid4().hex[:8]}"
            directory = Path(self.sandbox.get_runs_dir(run_id))
            if Path(self.sandbox.get_repo_path(run_id)).parent.exists():
                continue
            try:
                directory.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                continue
        with RunLock(directory / ".run.lock"):
            return await self._run_exclusive(task, run_id)

    async def resume(self, run_id: str) -> AgentRunResult:
        """Resume a compatible interrupted model/ready stage, without resetting budgets."""
        validate_run_id(run_id)
        directory = Path(self.sandbox.get_runs_dir(run_id))
        workspace = Path(self.sandbox.get_repo_path(run_id))
        if (
            directory.resolve() != directory
            or directory.resolve().parent != self.sandbox.runs_root
            or not directory.is_dir()
        ):
            raise ValueError("Run directory missing or outside runs root")
        if workspace.resolve() != workspace or workspace.parent.is_symlink():
            raise ValueError("Linked workspace cannot be resumed")
        with RunLock(directory / ".run.lock"):
            validate_manifest(self, run_id)
            if (directory / "failure.json").exists():
                raise ValueError(
                    "Persistence failure marked this run nonrecoverable; inspect manually"
                )
            checkpoint = Checkpoint.model_validate_json(
                (directory / "checkpoint.json").read_text(encoding="utf-8")
            )
            if checkpoint.schema_version != 2 or checkpoint.budget_semantics != "whole_task_v2":
                raise ValueError("Checkpoint version incompatible; inspect only, resume refused")
            if checkpoint.runtime_kind != self.runtime_kind:
                raise ValueError("Checkpoint belongs to a different runtime; resume refused")
            if checkpoint.run_id != run_id or checkpoint.state.run_id != run_id:
                raise ValueError("Checkpoint run ID mismatch")
            if checkpoint.stage not in {"ready", "llm_inflight"}:
                raise ValueError(
                    "Cannot resume terminal or in-flight tool/verifier; inspect manually"
                )
            if (directory / "result.json").exists() or checkpoint.state.phase in {
                "completed",
                "failed",
            }:
                raise ValueError("Terminal runs cannot be resumed")
            if checkpoint.purpose != "ordinary":
                raise ValueError("Evaluation runs require a fresh evaluation, not ordinary resume")
            if checkpoint.runtime != asdict(self.config) or checkpoint.identity != runtime_identity(
                self
            ):
                raise ValueError("Runtime/config/provider changed; resume refused")
            if recovery_inventory(workspace) != checkpoint.workspace:
                raise ValueError("Workspace changed since checkpoint")
            if recovery_inventory(directory / "trusted") != checkpoint.trusted:
                raise ValueError("Trusted evidence changed since checkpoint")
            return await self._run_exclusive(checkpoint.state.task, run_id, checkpoint)

    async def _run_exclusive(self, task, run_id, recovery=None):
        if getattr(self, "_executing", False):
            raise RuntimeError(
                "Legacy runner already active; use a RuntimePort for independent sessions"
            )
        self._executing = True
        try:
            return await self._run(task, run_id, recovery)
        finally:
            self._executing = False

    async def _run(
        self, task: DevelopmentTask, run_id: str, recovery: Checkpoint | None = None
    ) -> AgentRunResult:
        """Execute or restore the loop; synchronous preparation is measured separately."""
        self._trace_failure = None
        self._terminal_result = None
        start_time = recovery.started_at if recovery else time.time()
        self.session = RunSession(RunBudget.start(self.config, recovery))
        self.session.services.update(
            agent=self.agent,
            registry=self.registry,
            context=self.context_builder,
            state=self.state_manager,
            guards=self.loop_guard,
            verifier=self.verifier,
            decisions=self.decisions,
            tools=self.tools,
            acceptance=self.acceptance,
        )
        self.metrics = self.session.metrics
        self.verifier.last_results = self.session.validation
        for name in self.registry.names:
            tool = self.registry.get(name)
            if hasattr(tool, "cache"):
                tool.cache.clear()
                self.session.caches[name] = tool.cache
        self.metrics.reset()
        self.loop_guard.reset()
        self.file_cache.clear()
        self.request_count = 0
        self.budget_service = self.session.budget
        self.deadline = self.budget_service.deadline
        self.preparation_ms = 0

        self.attempts_in_turn = 0
        self.started_at = start_time
        self.deadline_at = self.budget_service.deadline_at
        self.identity = ""
        # 1. Initialize state
        state = recovery.state if recovery else self.state_manager.create(task, run_id)
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
            self._remaining()
            # 2. Create workspace and freeze trusted evidence before any action.
            if recovery:
                workspace_path = self.sandbox.get_repo_path(run_id)
                trusted = Path(self.sandbox.get_runs_dir(run_id)) / "trusted"
                self.identity = recovery.identity
                self.request_count = recovery.request_count
                self.attempts_in_turn = recovery.attempts_in_turn
                self.preparation_ms = recovery.preparation_ms
                self.deadline_at = recovery.deadline_at
                self.deadline = time.monotonic() + min(
                    recovery.remaining_seconds, recovery.deadline_at - time.time()
                )
                restore_fields(self.metrics, recovery.metrics)
                restore_fields(self.loop_guard, recovery.guard)
                if recovery.validation:
                    self.verifier.last_results[run_id] = recovery.validation
                # An interrupted model attempt may have been billed; usage is unknown.
                while len(self.metrics.llm_requests) < self.request_count:
                    self.metrics.record_llm_request(
                        {"status": "interrupted", "latency_ms": 0, "total_tokens": None}
                    )
                self._trace(run_id, state.total_steps, state.phase, "run_resumed")
            else:
                preparation_deadline = min(
                    self.deadline, time.monotonic() + self.config.preparation_timeout_seconds
                )
                with execution_scope(
                    deadline=preparation_deadline,
                    timeout_reason=(
                        "max_run_seconds"
                        if preparation_deadline == self.deadline
                        else "preparation_timeout_seconds"
                    ),
                ):
                    self.identity, workspace_path, trusted = await run_sync(self._prepare, run_id)
                self.preparation_ms = int((time.time() - start_time) * 1000)
                self.sandbox.save_artifact(
                    run_id, "run-manifest.json", manifest_for(self, run_id).model_dump_json(),
                )
            self._remaining()
            if self.verifier:
                self.verifier.bind_snapshot(run_id, trusted)
            if self.verifier:
                self.verifier.deadline = self.deadline

            return await self._execute_loop(state, workspace_path, trusted, start_time)

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
                "context_budget_exceeded"
                if isinstance(e, ContextBudgetExceeded)
                else "artifact_quota"
                if isinstance(e, ArtifactQuotaExceeded)
                else (str(e) or "run_timeout")
                if isinstance(e, TimeoutError)
                else "execution_error"
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

    async def _execute_loop(self, state, workspace_path, trusted, start_time):
        raise NotImplementedError

    def _prepare(self, run_id):
        identity = runtime_identity(self)
        self.sandbox.check_capacity(
            sum(
                path.stat().st_size
                for path in permitted_files(self.sandbox.base_repo, self.sandbox.base_repo)
            )
        )
        self.sandbox.check_artifacts(run_id)
        from devpilot.storage import CapacityReservation

        with CapacityReservation(
            self.sandbox.workspace_root,
            Path(self.sandbox.get_repo_path(run_id)).parent,
            self.sandbox.total_max_bytes,
            self.sandbox.max_bytes,
        ):
            workspace = self.sandbox.create(run_id)
        self.sandbox.check_artifacts(run_id, tree_bytes(Path(workspace)))
        with self.sandbox.admit_artifacts(run_id, tree_bytes(Path(workspace))):
            trusted = capture_snapshot(Path(workspace), Path(self.sandbox.get_runs_dir(run_id)))
        return identity, workspace, trusted

    def _remaining(self) -> float:
        if self._trace_failure is not None:
            raise self._trace_failure
        remaining = min(self.deadline - time.monotonic(), self.deadline_at - time.time())
        if remaining <= 0:
            raise BudgetExceeded("max_run_seconds")
        return remaining

    def _maybe_advance_phase(self, state: DevPilotState, decision: AgentDecision) -> None:
        """Auto-advance phase based on tool usage patterns."""
        old_phase = state.phase
        new_phase: str | None = None

        if state.phase == "understanding" and decision.action:
            if decision.action.tool.startswith("repo."):
                new_phase = "exploring"

        elif state.phase == "exploring":
            # Transition to planning if agent provides a plan or enough steps
            if decision.plan_update or state.total_steps >= 10:
                new_phase = "planning"
            # If agent starts using code tools, skip to implementing
            elif decision.action and (decision.action.tool.startswith("code.")):
                new_phase = "implementing"

        elif state.phase == "planning":
            if (
                decision.action and (decision.action.tool.startswith("code."))
            ) or state.total_steps >= 15:
                new_phase = "implementing"

        elif (
            state.phase == "implementing" and decision.action and decision.action.tool == "test.run"
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
            acceptance_coverage=(state.verification_report or {}).get("coverage", []),
            verification=state.verification_report,
            budget={
                "llm_requests": self.request_count,
                "max_llm_requests": self.config.max_llm_requests,
                "max_run_seconds": self.config.max_run_seconds,
                "preparation_ms": self.preparation_ms,
                **self.budget_service.snapshot(),
            },
        )

    def _save_artifacts(
        self,
        run_id: str,
        state: DevPilotState,
        result: AgentRunResult,
    ) -> None:
        """Save state.json and result.json to runs directory."""
        self._terminal_result = result
        if self._trace_failure is not None:
            result.artifact_errors.append(f"trace.jsonl: {type(self._trace_failure).__name__}")
        if result.error:
            result.error = redact(result.error, self.sandbox.secrets)
        if result.summary:
            result.summary = redact(result.summary, self.sandbox.secrets)
        self.metrics.total_steps = state.total_steps
        for path in state.modified_files:
            self.metrics.record_modified_file(path)
        try:
            self._checkpoint(state, "terminal")
        except OSError as exc:
            result.artifact_errors.append(f"checkpoint.json: {type(exc).__name__}")
        payloads = {
            "state.json": self.state_manager.serialize(state),
            "llm-requests.json": json.dumps(self.metrics.llm_requests, indent=2),
        }
        for name, content in payloads.items():
            try:
                self.sandbox.save_artifact(run_id, name, content)
            except OSError as exc:
                result.artifact_errors.append(f"{name}: {type(exc).__name__}")
        if result.artifact_errors:
            result.status = "failed"
            result.phase = "failed"
            result.termination_reason = result.termination_reason or "persistence_failed"
        try:
            data = json.loads(result.model_dump_json())
            data["metrics"] = self.metrics.to_dict()
            self.sandbox.save_artifact(run_id, "result.json", json.dumps(data, indent=2))
        except OSError as exc:
            result.artifact_errors.append(f"result.json: {type(exc).__name__}")
        if result.artifact_errors and any(
            "ArtifactQuotaExceeded" in error for error in result.artifact_errors
        ):
            # Never bypass an exhausted quota by exporting a complete checkpoint elsewhere.
            diagnostic = json.dumps(
                {
                    "run_id": run_id,
                    "recoverable": False,
                    "reason": "artifact_quota",
                    "errors": result.artifact_errors,
                }
            )
            with suppress(OSError):
                self.sandbox.save_artifact(run_id, "failure.json", diagnostic)
            return
        if result.artifact_errors:
            result.termination_reason = result.termination_reason or "persistence_failed"
            result.status = "failed"
            result.phase = "failed"
            recovery = Path(tempfile.gettempdir()) / "devpilot-recovery" / f"{run_id}.json"
            result.recovery_file = str(recovery)
            try:
                atomic_write(
                    recovery,
                    redact(
                        json.dumps(
                            {
                                "result": {"run_id": run_id},
                                "run_id": run_id,
                                "recoverable": False,
                                "artifact_errors": result.artifact_errors,
                                "termination_reason": result.termination_reason,
                            },
                            indent=2,
                        ),
                        self.sandbox.secrets,
                    ),
                )
            except OSError:
                result.recovery_file = None
                logging.error("Run artifacts and recovery write failed for %s", run_id)

    def _checkpoint(self, state: DevPilotState, stage: str = "ready") -> None:
        # Atomic authoritative state; failure prevents dispatch of another external action.
        directory = Path(self.sandbox.get_runs_dir(state.run_id))
        workspace = Path(self.sandbox.get_repo_path(state.run_id))
        checkpoint = Checkpoint(
            runtime_kind=self.runtime_kind,
            run_id=state.run_id,
            stage=stage,
            state=state,
            request_count=self.request_count,
            attempts_in_turn=self.attempts_in_turn,
            deadline_at=self.deadline_at,
            remaining_seconds=max(0, self.deadline - time.monotonic()) if self.deadline else 0,
            started_at=self.started_at,
            preparation_ms=self.preparation_ms,
            identity=self.identity,
            runtime=asdict(self.config),
            guard={k: v for k, v in vars(self.loop_guard).items() if k != "config"},
            metrics=dict(vars(self.metrics)),
            workspace=recovery_inventory(workspace) if workspace.is_dir() else {},
            trusted=recovery_inventory(directory / "trusted")
            if (directory / "trusted").is_dir()
            else {},
            purpose=self.purpose,
            validation=self.verifier.last_results.get(state.run_id, {}) if self.verifier else {},
            evaluation_seconds=self.budget_service.evaluation_seconds,
        )
        self.sandbox.save_artifact(
            state.run_id, "checkpoint.json", checkpoint.model_dump_json(indent=2)
        )
        self.sandbox.save_artifact(state.run_id, "state.json", self.state_manager.serialize(state))


# Preserve legacy accounting accessors while the data belongs to RunSession.
def _session_property(name):
    return property(
        lambda self: getattr(self.session, name),
        lambda self, value: setattr(self.session, name, value),
    )


for _name in ("request_count", "attempts_in_turn", "preparation_ms", "identity"):
    setattr(RuntimeLifecycle, _name, _session_property(_name))
