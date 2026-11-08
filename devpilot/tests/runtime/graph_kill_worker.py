"""Isolated fake-runtime worker for OS-kill recovery tests (no network clients)."""

import asyncio
import json
import sys
import threading
from pathlib import Path

from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.langgraph.operations import OperationJournal
from devpilot.runtime.langgraph.runner import LangGraphAgentRunner
from devpilot.tracing import TraceWriter
from tests.runtime import test_runner as helpers


def main():
    root, mode, point = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    helpers.CustomAgentRunner = LangGraphAgentRunner
    responses = [helpers._resp_finish()]
    if mode == "start" and not point.startswith("model_") and point != "terminal":
        responses.insert(0, helpers._resp_action(
            "code.create_file", path="new.py", content="x=1\n",
        ))
    runner = helpers._make_runner(responses, RuntimeConfig(), root / "baseline", root)
    runner.trace_writer = TraceWriter(str(runner.sandbox.runs_root))
    runner.trace_writer.artifact_store = runner.sandbox

    def ready(run_id):
        print(json.dumps({"ready": run_id}), flush=True)
        threading.Event().wait()  # Parent owns timeout and kills this exact child.

    if mode == "start":
        complete = OperationJournal.complete

        def intercepted(journal, operation_id, after, output):
            selected = (
                point.startswith("model_") and ":model:" in operation_id
                or point.startswith("tool_") and operation_id.endswith(":tool")
                or point.startswith("verify_") and ":verify:" in operation_id
            )
            if selected and point.endswith("prepared"):
                ready(journal.run_id)
            complete(journal, operation_id, after, output)
            if selected:
                ready(journal.run_id)

        OperationJournal.complete = intercepted
        if point == "terminal":
            runner._publish_terminal = lambda state, result: ready(state.run_id)
        asyncio.run(runner.run(helpers._make_task()))
        raise AssertionError("Expected crash window was not reached")
    run_id = sys.argv[4]
    try:
        result = asyncio.run(runner.resume(run_id))
        report = {"status": result.status, "error": result.error,
                  "requests": result.budget["llm_requests"], "steps": result.total_steps,
                  "unknown_requests": runner.metrics.to_dict()["llm_unknown_usage_requests"]}
    except Exception as exc:
        report = {"status": "refused", "error": str(exc)}
    report["calls"] = runner.agent.llm_client.call_count
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
