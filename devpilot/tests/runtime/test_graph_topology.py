"""Topology tests exercise the compiled graph, without model or filesystem I/O."""

import pytest

from devpilot.runtime.langgraph.graph import NODE_NAMES, build_graph


@pytest.mark.parametrize("fail_tool", [False, True])
async def test_serial_tool_and_verifier_route(fail_tool):
    visited = []
    decisions = iter([{"action": {"tool": "repo.read_file"}}, {"finish": {"summary": "done"}}])

    def node(name):
        async def invoke(state):
            visited.append(name)
            if name == "decide":
                return {"decision": next(decisions)}
            if name == "execute_tool" and fail_tool:
                raise ValueError("synthetic failure")
            if name == "verify":
                return {"verification_passed": True}
            if name == "finalize":
                return {"result": {"status": "failed" if state.get("failure") else "completed"}}
            return {}
        return invoke

    graph = build_graph({name: node(name) for name in NODE_NAMES})
    result = await graph.ainvoke({})
    if fail_tool:
        assert visited[-3:] == ["execute_tool", "fail", "finalize"]
        assert result["result"]["status"] == "failed"
    else:
        assert visited == [
            "prepare", "guard", "context", "decide", "execute_tool", "observe",
            "guard", "context", "decide", "verify", "finalize",
        ]
        assert result["result"]["status"] == "completed"
