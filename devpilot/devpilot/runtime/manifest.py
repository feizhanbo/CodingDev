"""Versioned local routing metadata; never contains provider credentials."""

from importlib.metadata import version
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from devpilot.runtime.shared.recovery import Checkpoint, validate_run_id


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    run_id: str
    runtime: Literal["custom", "langgraph"]
    llm_backend: Literal["fake", "openai", "langchain", "custom"]
    dependencies: dict[str, str]


def manifest_for(runner, run_id):
    client_type = type(runner.agent.llm_client)
    backend = {
        "devpilot.llm.fake.FakeLLMClient": "fake",
        "devpilot.llm.openai.OpenAIClient": "openai",
        "devpilot.llm.langchain.LangChainLLMClient": "langchain",
    }.get(client_type.__module__ + "." + client_type.__name__, "custom")
    packages = {"pydantic"}
    if backend in {"openai", "langchain"}:
        packages.add("openai")
    if backend == "langchain":
        packages.update({"langchain-core", "langchain-openai", "langsmith"})
    if runner.runtime_kind == "langgraph":
        packages.update({"langgraph", "langgraph-checkpoint", "langgraph-checkpoint-sqlite",
                         "langchain-core", "langsmith"})
    return RunManifest(run_id=run_id, runtime=runner.runtime_kind, llm_backend=backend,
                       dependencies={name: version(name) for name in sorted(packages)})


def read_manifest(runs_root, run_id):
    validate_run_id(run_id)
    root = Path(runs_root).resolve()
    directory = root / run_id
    path = directory / "run-manifest.json"
    if directory.resolve() != directory or path.resolve() != path:
        raise ValueError("Linked run manifest refused")
    if not path.exists():
        return None
    manifest = RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
    if manifest.run_id != run_id:
        raise ValueError("Run manifest identity mismatch")
    return manifest


def validate_manifest(runner, run_id):
    recorded = read_manifest(runner.sandbox.runs_root, run_id)
    if recorded is not None and recorded != manifest_for(runner, run_id):
        raise ValueError("Run engine, model adapter or dependency versions changed")


def read_legacy_checkpoint(runs_root, run_id):
    """Only validated pre-manifest custom checkpoints get the historical defaults."""
    validate_run_id(run_id)
    directory = Path(runs_root).resolve() / run_id
    path = directory / "checkpoint.json"
    if directory.resolve() != directory or path.resolve() != path:
        raise ValueError("Linked legacy checkpoint refused")
    graph = directory / "graph.sqlite"
    if graph.exists() or graph.is_symlink():
        raise ValueError("Graph checkpoint requires its original run manifest")
    if not path.exists():
        return None
    checkpoint = Checkpoint.model_validate_json(path.read_text(encoding="utf-8"))
    if checkpoint.runtime_kind != "custom":
        raise ValueError("Graph checkpoint requires its original run manifest")
    if checkpoint.run_id != run_id or checkpoint.state.run_id != run_id:
        raise ValueError("Legacy checkpoint identity mismatch")
    if checkpoint.schema_version != 2 or checkpoint.budget_semantics != "whole_task_v2":
        raise ValueError("Legacy checkpoint version incompatible; inspect only")
    return checkpoint
