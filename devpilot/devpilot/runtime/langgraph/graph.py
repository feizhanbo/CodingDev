"""Serial graph topology; execution services own business rules and side effects."""

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict, total=False):
    domain: dict[str, Any]
    decision: dict[str, Any]
    verification_passed: bool
    failure: dict[str, str]
    result: dict[str, Any]
    messages: list[dict[str, Any]]
    feedback: dict[str, Any] | None
    tool_result: dict[str, Any]
    tool_duration: int
    accounting: dict[str, Any]
    decision_id: str
    recovery: dict[str, Any]
    trace_sequence: int


Node = Callable[[GraphState], Awaitable[dict]]
NODE_NAMES = (
    "prepare", "guard", "context", "decide", "apply_plan", "execute_tool",
    "observe", "verify", "finalize", "fail",
)


def build_graph(nodes: dict[str, Node], *, checkpointer=None):
    """Compile one run's graph, injecting services without serializing clients.

    No implicit retries: model attempts and operation receipts are owned by nodes.
    Control-flow interrupts and cancellation propagate without being finalized.
    """
    missing = set(NODE_NAMES) - nodes.keys()
    if missing:
        raise ValueError(f"Missing graph services: {sorted(missing)}")
    builder = StateGraph(GraphState)

    def guarded(name):
        async def invoke(state):
            try:
                return await nodes[name](state)
            except GraphBubbleUp:
                raise
            except Exception as exc:
                return {"failure": {"node": name, "type": type(exc).__name__}}
        return invoke

    for name in NODE_NAMES:
        # Failure/finalization must propagate persistence failures to the outer
        # lifecycle handler; routing these back to fail would make an infinite loop.
        builder.add_node(name, nodes[name] if name in {"fail", "finalize"} else guarded(name))

    def next_or_fail(destination):
        return lambda state: "fail" if state.get("failure") else (
            "finalize" if state.get("result") else destination
        )

    builder.add_edge(START, "prepare")
    for source, destination in (
        ("prepare", "guard"), ("guard", "context"), ("context", "decide"),
        ("apply_plan", "guard"), ("execute_tool", "observe"), ("observe", "guard"),
    ):
        builder.add_conditional_edges(
            source, next_or_fail(destination), [destination, "fail", "finalize"],
        )

    def decision_route(state):
        if state.get("failure"):
            return "fail"
        decision = state.get("decision", {})
        branches = [key for key in ("action", "plan_update", "finish") if decision.get(key)]
        if len(branches) != 1:
            return "fail"
        return {"action": "execute_tool", "plan_update": "apply_plan", "finish": "verify"}[
            branches[0]
        ]

    builder.add_conditional_edges(
        "decide", decision_route, ["execute_tool", "apply_plan", "verify", "fail"],
    )
    builder.add_conditional_edges(
        "verify", lambda state: "fail" if state.get("failure") else (
            "finalize" if state.get("result") or state.get("verification_passed") else "guard"
        ), ["fail", "finalize", "guard"],
    )
    builder.add_edge("fail", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
