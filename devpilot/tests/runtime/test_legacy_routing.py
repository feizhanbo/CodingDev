"""Unversioned custom routing must survive a change to application defaults."""

import json
from types import SimpleNamespace

import pytest

from devpilot.application.runtime import CustomRuntime
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.shared.recovery import Checkpoint
from devpilot.runtime.shared.state_manager import StateManager
from devpilot.settings import Settings


@pytest.fixture
def legacy(tmp_path):
    identifier = "run_12345678"
    state = StateManager(RuntimeConfig()).create(DevelopmentTask(
        id="OLD", title="Old task", description="Old task", acceptance_criteria=[],
    ), identifier)
    saved = Checkpoint(
        run_id=identifier, stage="ready", state=state, request_count=0, attempts_in_turn=0,
        deadline_at=200, remaining_seconds=100, started_at=100, preparation_ms=0,
        identity="original", runtime={}, guard={}, metrics={}, workspace={}, trusted={},
    ).model_dump()
    saved.pop("runtime_kind")
    directory = tmp_path / identifier
    directory.mkdir()
    (directory / "checkpoint.json").write_text(json.dumps(saved), encoding="utf-8")
    return directory


async def test_old_custom_checkpoint_ignores_new_defaults(legacy):
    captured = []

    async def resume(identifier):
        return identifier

    def factory(**options):
        captured.append(options)
        return SimpleNamespace(resume_outcome=resume)

    settings = Settings(_env_file=None, runs_root=str(legacy.parent),
                        runtime="langgraph", llm_backend="langchain")
    runtime = CustomRuntime(factory=factory, settings=settings)
    assert await runtime.resume(legacy.name) == legacy.name
    assert captured[0]["settings"].runtime == "custom"
    assert captured[0]["settings"].llm_backend == "openai"
    assert settings.runtime == "langgraph"


async def test_unmanifested_graph_is_not_guessed_from_defaults(legacy):
    (legacy / "graph.sqlite").write_bytes(b"unidentified graph")

    def forbidden(**options):
        raise AssertionError("Ambiguous graph must be refused before building a model")

    runtime = CustomRuntime(factory=forbidden, settings=Settings(
        _env_file=None, runs_root=str(legacy.parent), runtime="custom",
    ))
    with pytest.raises(ValueError, match="manifest"):
        await runtime.resume(legacy.name)
