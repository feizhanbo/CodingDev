"""Offline framework feasibility probe; run in the isolated framework venv."""

import asyncio
import json
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    count: int


async def increment(state: State):
    return {"count": state["count"] + 1}


async def main():
    builder = StateGraph(State)
    builder.add_node("increment", increment)
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)
    config = {"configurable": {"thread_id": "probe"}}
    with tempfile.TemporaryDirectory() as directory:
        database = str(Path(directory) / "checkpoint.sqlite")
        async with AsyncSqliteSaver.from_conn_string(database) as saver:
            graph = builder.compile(checkpointer=saver)
            result = await graph.ainvoke({"count": 0}, config, durability="sync")
            assert result["count"] == 1
        async with AsyncSqliteSaver.from_conn_string(database) as saver:
            graph = builder.compile(checkpointer=saver)
            state = await graph.aget_state(config)
            assert state.values == {"count": 1}
            assert not state.next
    model = ChatOpenAI(model="probe", api_key="synthetic-not-a-key", max_retries=0)
    assert model.max_retries == 0
    model.bind(response_format={"type": "json_object"})
    print(json.dumps({
        "versions": {name: version(name) for name in (
            "langgraph", "langchain-core", "langchain-openai", "langgraph-checkpoint-sqlite"
        )},
        "async_graph": "PASS", "sqlite_reopen": "PASS", "model_config": "PASS",
        "model_requests": 0,
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
