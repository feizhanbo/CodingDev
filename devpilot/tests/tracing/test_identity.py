"""Stable node identities make trace replay idempotent without a separate index."""

import json
from types import SimpleNamespace

import pytest

from devpilot.runtime.langgraph.runner import LangGraphAgentRunner
from devpilot.tracing import TraceWriter
from devpilot.tracing.identity import trace_scope


def test_reopened_writer_deduplicates_same_node_but_retains_next_node(tmp_path):
    for _ in range(2):
        writer = TraceWriter(str(tmp_path))
        with trace_scope("run:node:4:observe"):
            writer.write_event("run", 1, "implementing", "tool_result")
            writer.write_event("run", 1, "implementing", "phase_changed")
    with trace_scope("run:node:8:observe"):
        writer.write_event("run", 2, "implementing", "tool_result")
    lines = (tmp_path / "run" / "trace.jsonl").read_text().splitlines()
    events = [json.loads(line) for line in lines]
    assert [event["event"] for event in events] == ["tool_result", "phase_changed", "tool_result"]
    assert len({event["event_id"] for event in events}) == 3


def test_missing_prior_event_does_not_shift_other_event_identity(tmp_path):
    writer = TraceWriter(str(tmp_path))
    with trace_scope("node"):
        writer.write_event("run", 0, "exploring", "llm_request")
        writer.write_event("run", 0, "exploring", "agent_decision")
    with trace_scope("node"):
        writer.write_event("run", 0, "exploring", "agent_decision")
    assert len((tmp_path / "run" / "trace.jsonl").read_text().splitlines()) == 2


def test_failed_write_does_not_consume_event_identity(tmp_path, monkeypatch):
    writer = TraceWriter(str(tmp_path))

    def fail(*args):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr("devpilot.tracing.writer.atomic_write", fail)
        with trace_scope("node"), pytest.raises(OSError):
            writer.write_event("run", 0, "exploring", "agent_decision")
    with trace_scope("node"):
        writer.write_event("run", 0, "exploring", "agent_decision")
    assert len((tmp_path / "run" / "trace.jsonl").read_text().splitlines()) == 1


def test_incomplete_existing_trace_is_not_silently_discarded(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    path = folder / "trace.jsonl"
    path.write_text('{"event":')
    with trace_scope("node"), pytest.raises(OSError, match="incomplete"):
        TraceWriter(str(tmp_path)).write_event("run", 0, "exploring", "agent_decision")
    assert path.read_text() == '{"event":'


def test_new_model_attempt_is_not_deduplicated_against_interrupted_attempt(tmp_path):
    runner = LangGraphAgentRunner.__new__(LangGraphAgentRunner)
    runner.session = SimpleNamespace(request_count=1)
    runner.trace_writer = TraceWriter(str(tmp_path))
    runner._in_graph_node = runner._graph_running = True
    for number in (1, 2, 2):
        runner.request_count = number
        with trace_scope("same-replayed-decide-node"):
            runner._trace("run", 0, "understanding", "llm_request", data={"attempt": number})
    lines = (tmp_path / "run" / "trace.jsonl").read_text().splitlines()
    assert [json.loads(line)["data"]["attempt"] for line in lines] == [1, 2]
