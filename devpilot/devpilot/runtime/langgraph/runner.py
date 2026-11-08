"""Graph execution reusing the existing locked lifecycle and business steps.

Recovery restores graph state and reconciles durable operation receipts.
"""

import time
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from langgraph.errors import GraphBubbleUp
from langsmith import tracing_context

from devpilot.domain.decision import AgentDecision
from devpilot.domain.result import AgentRunResult
from devpilot.domain.state import DevPilotState
from devpilot.llm.base import LLMMessage
from devpilot.runtime.langgraph.checkpointer import open_checkpointer
from devpilot.runtime.langgraph.graph import NODE_NAMES, build_graph
from devpilot.runtime.langgraph.operations import ManualRecoveryRequired, OperationJournal, digest
from devpilot.runtime.langgraph.recovery import checkpoint_from_graph
from devpilot.runtime.manifest import validate_manifest
from devpilot.runtime.shared.lifecycle import RuntimeLifecycle
from devpilot.runtime.shared.loop_guard import GuardrailViolation
from devpilot.runtime.shared.recovery import (
    recovery_inventory,
    restore_fields,
    runtime_identity,
    validate_run_id,
)
from devpilot.security import permitted_files
from devpilot.storage import RunLock, tree_bytes
from devpilot.tools.context import ToolResult
from devpilot.tracing.identity import trace_scope
from devpilot.verification.verifier import VerificationResult


class LangGraphAgentRunner(RuntimeLifecycle):
    runtime_kind = "langgraph"

    def _save_artifacts(self, run_id, state, result):
        if getattr(self, "_graph_running", False):
            # The result remains graph state until sync durability has succeeded.
            return
        super()._save_artifacts(run_id, state, result)

    def _emit(self, event_type, data):
        terminal = event_type in {"run_completed", "run_failed"} or (
            event_type == "phase_changed" and data.get("to") in {"completed", "failed"}
        )
        if getattr(self, "_graph_running", False) and terminal:
            self._terminal_events.append((event_type, deepcopy(data)))
            return
        super()._emit(event_type, data)

    def _trace(self, run_id, step, phase, event, tool=None, arguments_summary=None, data=None):
        if getattr(self, "_graph_running", False) and event in {"run_completed", "run_failed"}:
            self._terminal_traces.append((
                run_id, step, phase, event, tool, arguments_summary, deepcopy(data),
            ))
            return
        if event == "llm_request":
            with trace_scope(f"{run_id}:model-request:{self.request_count}"):
                super()._trace(run_id, step, phase, event, tool, arguments_summary, data)
        elif getattr(self, "_in_graph_node", False):
            super()._trace(run_id, step, phase, event, tool, arguments_summary, data)
        else:
            with trace_scope(f"{run_id}:lifecycle:{step}:{self.request_count}:{event}"):
                super()._trace(run_id, step, phase, event, tool, arguments_summary, data)

    def _publish_terminal(self, state, result):
        self._save_artifacts(state.run_id, state, result)
        for args in self._terminal_traces:
            if args[3] == "run_completed" and result.status != "completed":
                continue
            self._trace(*args)
        had_success = any(e == "run_completed" for e, _ in self._terminal_events)
        if result.status == "failed" and had_success:
            self._trace(state.run_id, state.total_steps, "failed", "run_failed",
                        data={"reason": result.termination_reason or result.error})
            self._emit("run_failed", {
                "task_id": state.task.id, "run_id": state.run_id,
                "error": result.termination_reason or result.error,
            })
        else:
            for event, data in self._terminal_events:
                self._emit(event, data)
        return result

    async def _verify_candidate(self, state, workspace_path):
        directory = Path(self.sandbox.get_runs_dir(state.run_id))

        def fingerprint():
            return digest({
                "workspace": recovery_inventory(Path(workspace_path)),
                "trusted": recovery_inventory(directory / "trusted"),
            })

        def evidence_fingerprint(report):
            if report.evidence_ref is None:
                return None
            path = Path(report.evidence_ref)
            if path.resolve() != path.absolute() or not path.resolve().is_relative_to(directory):
                raise ManualRecoveryRequired("Verification evidence escapes run directory")
            return digest(recovery_inventory(path))

        journal = OperationJournal(self.sandbox, state.run_id)
        operation_id = f"{state.run_id}:verify:{self.request_count}"
        previous = journal.begin(operation_id, {
            "task": state.task.model_dump(), "request_count": self.request_count,
        }, fingerprint(), admission={"budget": self.budget_service.snapshot()})
        if previous is not None:
            report = VerificationResult.model_validate(previous["verification"])
            if evidence_fingerprint(report) != previous["evidence_digest"]:
                raise ManualRecoveryRequired("Verification evidence changed")
            self.budget_service.evaluation_seconds = max(
                self.budget_service.evaluation_seconds,
                previous["budget"]["evaluation_seconds"],
            )
            self.verifier.last_results[state.run_id] = previous["evidence"]
            return report
        report = await super()._verify_candidate(state, workspace_path)
        journal.complete(operation_id, fingerprint(), {
            "verification": report.model_dump(),
            "evidence": self.verifier.last_results.get(state.run_id, {}),
            "evidence_digest": evidence_fingerprint(report),
            "budget": self.budget_service.snapshot(),
        })
        return report

    def _begin_model_request(self, state, messages):
        journal = OperationJournal(self.sandbox, state.run_id)
        operation_id = f"{state.run_id}:model:{self.request_count}"
        previous = journal.begin(operation_id, {
            "messages": [m.model_dump() for m in messages],
            "attempt": self.attempts_in_turn,
            "request_count": self.request_count,
        }, "model-request", admission={
            "request_count": self.request_count,
            "attempts_in_turn": self.attempts_in_turn,
            "budget": self.budget_service.snapshot(),
        })
        if previous is not None:
            raise ManualRecoveryRequired("Model receipt must be reconciled before dispatch")

    def _end_model_request(self, state, decision):
        record = self.agent.last_request
        if record is None:
            self.metrics.record_llm_request({
                "request_id": f"{state.run_id}:model:{self.request_count}",
                "status": "unknown", "total_tokens": None, "latency_ms": 0,
                "attempt": self.attempts_in_turn, "step": state.total_steps,
            })
        OperationJournal(self.sandbox, state.run_id).complete(
            f"{state.run_id}:model:{self.request_count}", "model-request", {
                "request_count": self.request_count,
                "attempts_in_turn": self.attempts_in_turn,
                "decision": decision.model_dump() if decision is not None else None,
                "request": record.model_dump() if record is not None else None,
                "budget": self.budget_service.snapshot(),
                "metrics": deepcopy(vars(self.metrics)),
            },
        )

    def _reconcile_model_requests(self, state, messages):
        journal = OperationJournal(self.sandbox, state.run_id)
        while True:
            number = self.request_count + 1
            receipt = journal.read(f"{state.run_id}:model:{number}")
            if receipt is None:
                return None
            attempt = self.attempts_in_turn + 1
            expected = digest({"messages": [m.model_dump() for m in messages],
                               "attempt": attempt, "request_count": number})
            if receipt.identity != expected or attempt > 3:
                raise ManualRecoveryRequired("Model receipt does not match interrupted turn")
            saved = receipt.admission
            if receipt.stage == "completed":
                if receipt.output is None or digest(receipt.output) != receipt.output_digest:
                    raise ManualRecoveryRequired("Model receipt changed or was redacted")
                saved = receipt.output
            if (saved is None or saved["request_count"] != number
                    or saved["attempts_in_turn"] != attempt):
                raise ManualRecoveryRequired("Model receipt accounting mismatch")
            budget = saved["budget"]
            current = self.budget_service
            if (budget["started_at"] != current.started_at
                    or budget["deadline_at"] != current.deadline_at
                    or budget["budget_semantics"] != "whole_task_v2"):
                raise ManualRecoveryRequired("Model receipt budget origin mismatch")
            current.evaluation_seconds = max(
                current.evaluation_seconds, budget["evaluation_seconds"],
            )
            current.deadline = min(current.deadline, time.monotonic() + budget["remaining_seconds"])
            self.deadline = current.deadline
            self.request_count, self.attempts_in_turn = number, attempt
            if receipt.stage == "completed":
                restore_fields(self.metrics, saved["metrics"])
                if saved["decision"] is not None:
                    self._remaining()
                    return AgentDecision.model_validate(saved["decision"])
            else:
                self.metrics.record_llm_request({
                    "status": "interrupted", "total_tokens": None, "latency_ms": 0,
                    "attempt": attempt, "step": state.total_steps,
                })

    async def decide_step(self, state, messages):
        recovered = self._reconcile_model_requests(state, messages)
        if recovered is not None:
            return recovered
        return await super().decide_step(state, messages)

    async def resume(self, run_id):
        validate_run_id(run_id)
        directory = Path(self.sandbox.get_runs_dir(run_id))
        workspace = Path(self.sandbox.get_repo_path(run_id))
        if (directory.resolve() != directory or directory.parent != self.sandbox.runs_root
                or not directory.is_dir() or workspace.resolve() != workspace):
            raise ValueError("Run directory missing or linked")
        with RunLock(directory / ".run.lock"):
            validate_manifest(self, run_id)
            if (directory / "result.json").exists() or (directory / "failure.json").exists():
                raise ValueError("Terminal or persistence-failed run cannot be resumed")
            if not (directory / "graph.sqlite").is_file():
                raise ValueError("Graph checkpoint missing")

            async def inspect_only(_):
                raise RuntimeError("Inspection graph must never execute")

            async with open_checkpointer(self.sandbox, run_id) as saver:
                graph = build_graph(dict.fromkeys(NODE_NAMES, inspect_only), checkpointer=saver)
                snapshot = await graph.aget_state({"configurable": {"thread_id": run_id}})
            values = snapshot.values
            checkpoint = checkpoint_from_graph(
                values, run_id=run_id, runtime=asdict(self.config), identity=runtime_identity(self),
            )
            if checkpoint.purpose != "ordinary" or values.get("failure"):
                raise ValueError("Evaluation or failed graph requires manual inspection")
            actual_workspace = recovery_inventory(workspace)
            actual_trusted = recovery_inventory(directory / "trusted")
            if actual_trusted != checkpoint.trusted:
                raise ValueError("Trusted evidence changed since graph checkpoint")
            if actual_workspace != checkpoint.workspace:
                # An operation may have completed after the last graph checkpoint.
                # Only its durable receipt can authorize this newer file inventory.
                next_node = snapshot.next[0] if len(snapshot.next) == 1 else None
                suffix = {"execute_tool": "tool", "verify": "verify"}.get(next_node)
                if suffix is None:
                    raise ValueError("Workspace changed since graph checkpoint")
                operation_id = (values["decision_id"] + ":tool" if suffix == "tool"
                                else f"{run_id}:verify:{checkpoint.request_count}")
                receipt = OperationJournal(self.sandbox, run_id).read(operation_id)
                current = digest({"workspace": actual_workspace, "trusted": actual_trusted})
                if receipt is None or receipt.stage != "completed" or receipt.after != current:
                    raise ManualRecoveryRequired("Workspace has uncertain operation effects")
            self._resuming_graph = True
            try:
                return await self._run_exclusive(checkpoint.state.task, run_id, checkpoint)
            finally:
                self._resuming_graph = False

    async def _execute_loop(self, state, workspace_path, trusted, start_time):
        # Graph schedules every business operation; the inherited custom loop
        # is never invoked. Ephemeral dependencies stay outside serialized state.
        pending = {}
        journal = OperationJournal(self.sandbox, state.run_id)

        def workspace_digest():
            return digest({
                "workspace": recovery_inventory(Path(workspace_path)),
                "trusted": recovery_inventory(trusted),
            })

        async def prepare(_):
            return {"domain": state.model_dump()}

        async def guard(_):
            if state.total_steps >= self.config.max_steps:
                result = self.max_steps_step(state, start_time)
                return {"domain": state.model_dump(), "result": result.model_dump()}
            self._remaining()
            self._checkpoint(state)
            self.sandbox.check_artifacts(state.run_id)
            if tree_bytes(Path(workspace_path)) > self.sandbox.max_bytes:
                raise GuardrailViolation("workspace_max_bytes")
            self.loop_guard.check_max_steps(state)
            return {}

        async def context(_):
            messages = self.context_builder.build(state, workspace_path)
            return {"messages": [message.model_dump() for message in messages]}

        async def decide(snapshot):
            decision = await self.decide_step(
                state, [LLMMessage.model_validate(m) for m in snapshot["messages"]]
            )
            kind = "finish" if decision.finish else "action" if decision.action else "plan_update"
            self._emit("agent_decision", {
                "task_id": state.task.id, "phase": state.phase, "decision_type": kind,
            })
            self._trace(state.run_id, state.total_steps, state.phase, "agent_decision",
                        data={"decision_type": kind})
            feedback = self.loop_guard.check_plan_update_loop(
                decision, state.phase, state.repair_required,
            )
            if feedback:
                self._trace(state.run_id, state.total_steps, state.phase, "guardrail_triggered",
                            data=feedback)
            return {
                "decision": decision.model_dump(), "feedback": feedback, "messages": [],
                "decision_id": f"{state.run_id}:{self.request_count}",
            }

        def finish_turn(snapshot):
            self.plan_feedback_step(
                state, AgentDecision.model_validate(snapshot["decision"]), snapshot.get("feedback")
            )
            self.attempts_in_turn = 0
            self._checkpoint(state)
            return {"domain": state.model_dump()}

        async def apply_plan(snapshot):
            return finish_turn(snapshot)

        async def execute_tool(snapshot):
            operation_id = snapshot["decision_id"] + ":tool"
            previous = journal.begin(operation_id, snapshot["decision"], workspace_digest())
            if previous is not None:
                return previous
            tool, duration = await self.execute_tool_step(
                state, AgentDecision.model_validate(snapshot["decision"]), workspace_path, trusted,
            )
            output = {"tool_result": tool.model_dump(), "tool_duration": duration}
            journal.complete(operation_id, workspace_digest(), output)
            return output

        async def observe(snapshot):
            result = self.observe_step(
                state, AgentDecision.model_validate(snapshot["decision"]),
                ToolResult.model_validate(snapshot["tool_result"]), snapshot["tool_duration"],
                start_time,
            )
            if result is not None:
                return {"domain": state.model_dump(), "result": result.model_dump()}
            return finish_turn(snapshot)

        async def verify(snapshot):
            files = permitted_files(Path(workspace_path), Path(workspace_path))
            result = await self.verify_step(
                state, AgentDecision.model_validate(snapshot["decision"]),
                workspace_path, trusted, files, start_time,
            )
            if result is not None:
                return {"domain": state.model_dump(), "result": result.model_dump()}
            return {"domain": state.model_dump(), "verification_passed": False}

        async def fail(_):
            # Preserve original exception semantics in the locked lifecycle.
            raise pending.pop("error", ValueError("Invalid graph decision"))

        async def finalize(snapshot):
            return {"result": snapshot["result"]}

        def accounting():
            return deepcopy({
                "request_count": self.request_count,
                "attempts_in_turn": self.attempts_in_turn,
                "budget": self.budget_service.snapshot(),
                "guard": {k: v for k, v in vars(self.loop_guard).items() if k != "config"},
                "metrics": vars(self.metrics),
                "validation": self.verifier.last_results.get(state.run_id, {})
                if self.verifier else {},
            })

        def recovery_metadata():
            return {
                "schema_version": 1, "runtime_kind": self.runtime_kind,
                "run_id": state.run_id, "identity": self.identity,
                "runtime": asdict(self.config), "purpose": self.purpose,
                "started_at": self.budget_service.started_at, "deadline_at": self.deadline_at,
                "preparation_ms": self.preparation_ms,
                "workspace": recovery_inventory(Path(workspace_path)),
                "trusted": recovery_inventory(trusted),
            }

        def capture(node, name):
            async def invoke(snapshot):
                # Work on a validated copy; the graph input is never mutated.
                restored = DevPilotState.model_validate(snapshot["domain"])
                state.__dict__.update(restored.__dict__)
                sequence = snapshot.get("trace_sequence", 0) + 1
                try:
                    self._in_graph_node = True
                    with trace_scope(f"{state.run_id}:node:{sequence}:{name}"):
                        update = await node(snapshot)
                    recovery = (recovery_metadata() if name in {"prepare", "execute_tool", "verify"}
                                else snapshot["recovery"])
                    return {**update, "domain": state.model_dump(), "accounting": accounting(),
                            "recovery": recovery, "trace_sequence": sequence}
                except GraphBubbleUp:
                    raise
                except Exception as exc:
                    if name in {"fail", "finalize"}:
                        raise
                    pending["error"] = exc
                    return {
                        "domain": state.model_dump(), "accounting": accounting(),
                        "failure": {"node": name, "type": type(exc).__name__},
                    }
                finally:
                    self._in_graph_node = False
            return invoke

        nodes = {
            "prepare": prepare, "guard": guard, "context": context, "decide": decide,
            "apply_plan": apply_plan, "execute_tool": execute_tool, "observe": observe,
            "verify": verify, "fail": fail, "finalize": finalize,
        }
        self._terminal_events = []
        self._terminal_traces = []
        self._graph_running = True
        try:
            async with open_checkpointer(self.sandbox, state.run_id) as saver:
                graph = build_graph(
                    {name: capture(node, name) for name, node in nodes.items()}, checkpointer=saver,
                )
                with tracing_context(enabled=False):
                    graph_input = (None if getattr(self, "_resuming_graph", False) else {
                        "domain": state.model_dump(), "accounting": accounting(),
                        "recovery": recovery_metadata(),
                    })
                    final = await graph.ainvoke(
                        graph_input,
                        {"configurable": {"thread_id": state.run_id},
                         "recursion_limit": 12 * (self.config.max_llm_requests + 1)},
                        durability="sync",
                    )
        except Exception:
            # A persistence failure after verifier success is not a completed run.
            if state.phase == "completed":
                state.phase = "failed"
            raise
        finally:
            self._graph_running = False
        result = AgentRunResult.model_validate(final["result"])
        if not self._terminal_events:
            # A completed graph can outlive a crash before terminal publication.
            event = "run_completed" if result.status == "completed" else "run_failed"
            self._terminal_events.append((event, {"run_id": state.run_id,
                                                "task_id": state.task.id,
                                                "status": result.status}))
            self._terminal_traces.append((state.run_id, state.total_steps, result.phase,
                                          event, None, None, None))
        return self._publish_terminal(state, result)
