"""No terminal notification precedes durable graph completion and artifact writes."""

from types import SimpleNamespace

import pytest

from devpilot.domain.result import AgentRunResult
from devpilot.runtime.langgraph.runner import LangGraphAgentRunner
from devpilot.runtime.shared.lifecycle import RuntimeLifecycle


@pytest.mark.parametrize("artifact_failure", [False, True])
def test_terminal_publication_is_deferred(monkeypatch, artifact_failure):
    calls = []

    def save(self, run_id, state, result):
        calls.append("save")
        if artifact_failure:
            result.status = result.phase = "failed"
            result.termination_reason = "persistence_failed"

    monkeypatch.setattr(RuntimeLifecycle, "_save_artifacts", save)
    monkeypatch.setattr(RuntimeLifecycle, "_emit", lambda self, event, data: calls.append(event))
    monkeypatch.setattr(RuntimeLifecycle, "_trace",
                        lambda self, *args: calls.append("trace:" + args[3]))
    runner = LangGraphAgentRunner.__new__(LangGraphAgentRunner)
    runner.session = SimpleNamespace(request_count=1)
    runner._graph_running = True
    runner._terminal_events = []
    runner._terminal_traces = []
    state = SimpleNamespace(run_id="run", total_steps=1, task=SimpleNamespace(id="task"))
    result = AgentRunResult(
        run_id="run", task_id="task", status="completed", phase="completed", total_steps=1,
    )
    runner._save_artifacts("run", state, result)
    runner._emit("phase_changed", {"to": "completed"})
    runner._emit("run_completed", {"status": "completed"})
    runner._trace("run", 1, "completed", "run_completed")
    assert calls == []
    runner._graph_running = False
    runner._publish_terminal(state, result)
    assert calls[0] == "save"
    if artifact_failure:
        assert calls == ["save", "trace:run_failed", "run_failed"]
    else:
        assert calls == ["save", "trace:run_completed", "phase_changed", "run_completed"]
