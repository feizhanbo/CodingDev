"""The real graph must satisfy the existing deterministic business contract."""

from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from devpilot.application.factory import create_runtime
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.contracts import RunRequest
from devpilot.runtime.langgraph.checkpointer import QuotaSqliteSaver
from devpilot.runtime.langgraph.operations import Receipt
from devpilot.runtime.langgraph.recovery import checkpoint_from_graph
from devpilot.settings import Settings
from tests.contracts.runtime import assert_smoke_contract


@pytest.mark.parametrize("fail_terminal_write", [False, True])
async def test_graph_smoke_contract(tmp_path, monkeypatch, fail_terminal_write):
    events = []
    terminal_writes = []
    original = QuotaSqliteSaver.aput

    async def checked_put(saver, config, checkpoint, metadata, new_versions):
        if checkpoint["channel_values"].get("result"):
            terminal_writes.append(checkpoint["id"])
            assert not (Path(saver.sandbox.get_runs_dir(saver.run_id)) / "result.json").exists()
            assert "run_completed" not in events
            if fail_terminal_write:
                raise OSError("terminal checkpoint unavailable")
        return await original(saver, config, checkpoint, metadata, new_versions)

    monkeypatch.setattr(QuotaSqliteSaver, "aput", checked_put)
    runtime = create_runtime(fake=True, on_event=lambda event, _: events.append(event),
                             settings=Settings(
        _env_file=None, runtime="langgraph", workspace_root=str(tmp_path / "ws"),
        runs_root=str(tmp_path / "runs"),
    ))
    outcome = await runtime.execute(RunRequest(DevelopmentTask(
        id="GRAPH", title="Fix addition", description="Fix addition",
        acceptance_criteria=["Addition is correct", "Add tests"],
    )))
    assert terminal_writes
    if fail_terminal_write:
        assert outcome.result.status == "failed"
        assert "terminal checkpoint unavailable" in outcome.result.error
        assert "run_completed" not in events
        assert "run_failed" in events
        return
    assert events.count("run_completed") == 1
    assert_smoke_contract(outcome.result, outcome.state, outcome.final_diff)
    receipts = [Receipt.model_validate_json(p.read_text(encoding="utf-8"))
                for p in (Path(outcome.artifacts) / "operations").glob("*.json")]
    model_receipts = [r for r in receipts if ":model:" in r.operation_id]
    assert sorted(r.admission["request_count"] for r in model_receipts) == list(range(1, 9))
    assert all(r.stage == "completed" for r in model_receipts)
    async with AsyncSqliteSaver.from_conn_string(outcome.artifacts + "/graph.sqlite") as saver:
        saved = await saver.aget_tuple({"configurable": {"thread_id": outcome.result.run_id}})
        channels = saved.checkpoint["channel_values"]
        assert channels["domain"]["total_steps"] == 7
        assert channels["accounting"]["request_count"] == 8
        assert channels["result"]["status"] == "completed"
        recovery = checkpoint_from_graph(
            channels, run_id=outcome.result.run_id,
            runtime=channels["recovery"]["runtime"], identity=channels["recovery"]["identity"],
        )
        assert recovery.stage == "terminal"
        assert recovery.request_count == 8
        assert recovery.state.total_steps == 7
        assert recovery.workspace
        assert recovery.trusted


@pytest.mark.parametrize("limit", ["max_steps", "max_llm_requests"])
async def test_graph_budget_verdict_matches_custom(tmp_path, limit):
    results = []
    for backend in ("custom", "langgraph"):
        runtime = create_runtime(fake=True, settings=Settings(
            _env_file=None, runtime=backend, **{limit: 1},
            workspace_root=str(tmp_path / backend / "ws"),
            runs_root=str(tmp_path / backend / "runs"),
        ))
        outcome = await runtime.execute(RunRequest(DevelopmentTask(
            id="LIMIT", title="Fix addition", description="Fix addition",
            acceptance_criteria=["Addition is correct", "Add tests"],
        )))
        result = outcome.result
        assert result.status == "failed"
        results.append((
            result.total_steps, result.error, result.termination_reason,
            result.budget["llm_requests"], [o.name for o in result.observations],
        ))
    assert results[0] == results[1]
