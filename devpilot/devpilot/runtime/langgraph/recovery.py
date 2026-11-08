"""Project one coherent graph snapshot into the shared session recovery contract."""

from devpilot.runtime.shared.recovery import Checkpoint


def checkpoint_from_graph(values, *, run_id, runtime, identity):
    metadata = values["recovery"]
    accounting = values["accounting"]
    budget = accounting["budget"]
    if metadata["schema_version"] != 1 or metadata["runtime_kind"] != "langgraph":
        raise ValueError("Unsupported graph recovery schema")
    if metadata["run_id"] != run_id or values["domain"]["run_id"] != run_id:
        raise ValueError("Graph run identity mismatch")
    if metadata["runtime"] != runtime or metadata["identity"] != identity:
        raise ValueError("Graph runtime/config/provider changed")
    if budget["budget_semantics"] != "whole_task_v2":
        raise ValueError("Unsupported graph budget semantics")
    if (budget["started_at"] != metadata["started_at"]
            or budget["deadline_at"] != metadata["deadline_at"]):
        raise ValueError("Graph budget origin changed")
    return Checkpoint(
        runtime_kind="langgraph", run_id=run_id,
        stage="terminal" if values.get("result") else "ready",
        state=values["domain"],
        request_count=accounting["request_count"],
        attempts_in_turn=accounting["attempts_in_turn"],
        started_at=metadata["started_at"], deadline_at=metadata["deadline_at"],
        remaining_seconds=budget["remaining_seconds"],
        evaluation_seconds=budget["evaluation_seconds"],
        preparation_ms=metadata["preparation_ms"],
        identity=identity, runtime=runtime,
        metrics=accounting["metrics"], guard=accounting["guard"],
        validation=accounting.get("validation", {}),
        workspace=metadata["workspace"], trusted=metadata["trusted"],
        purpose=metadata["purpose"],
    )
