"""Resume routing uses recorded backends and validates dependency compatibility."""

from types import SimpleNamespace

import pytest

from devpilot.application.factory import create_runtime
from devpilot.application.runtime import CustomRuntime
from devpilot.runtime.langgraph.runner import LangGraphAgentRunner
from devpilot.runtime.manifest import RunManifest, read_manifest, validate_manifest
from devpilot.settings import Settings


def save(tmp_path, **changes):
    manifest = RunManifest(run_id="run_12345678", runtime="langgraph",
                           llm_backend="fake", dependencies={}).model_copy(update=changes)
    folder = tmp_path / manifest.run_id
    folder.mkdir(exist_ok=True)
    (folder / "run-manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return manifest


@pytest.mark.parametrize("backend", ["fake", "openai", "langchain"])
async def test_resume_routes_without_mutating_current_settings(tmp_path, backend):
    save(tmp_path, llm_backend=backend)
    settings = Settings(_env_file=None, runtime="custom", llm_backend="openai",
                        runs_root=str(tmp_path))
    calls = []

    async def resume(run_id):
        return run_id

    def factory(**options):
        calls.append(options)
        return SimpleNamespace(resume_outcome=resume)

    runtime = CustomRuntime(factory=factory, settings=settings)
    assert await runtime.resume("run_12345678") == "run_12345678"
    assert calls[0]["settings"].runtime == "langgraph"
    assert calls[0]["fake"] == (backend == "fake")
    if backend != "fake":
        assert calls[0]["settings"].llm_backend == backend
    assert settings.runtime == "custom"
    assert settings.llm_backend == "openai"


def test_manifest_identity_and_schema_validation(tmp_path):
    save(tmp_path, schema_version=2)
    with pytest.raises(ValueError):
        read_manifest(tmp_path, "run_12345678")
    with pytest.raises(ValueError, match="Invalid run ID"):
        read_manifest(tmp_path, "../outside")


def test_dependency_drift_refused(tmp_path, monkeypatch):
    recorded = save(tmp_path, dependencies={"langgraph": "old"})
    runner = SimpleNamespace(sandbox=SimpleNamespace(runs_root=tmp_path))
    monkeypatch.setattr("devpilot.runtime.manifest.manifest_for", lambda *_:
                        recorded.model_copy(update={"dependencies": {"langgraph": "new"}}))
    with pytest.raises(ValueError, match="dependency versions changed"):
        validate_manifest(runner, "run_12345678")


async def test_real_bootstrap_selects_recorded_graph_and_fake_client(tmp_path, monkeypatch):
    save(tmp_path)

    async def inspect_runner(self, run_id):
        return self.runtime_kind, type(self.agent.llm_client).__name__

    monkeypatch.setattr(LangGraphAgentRunner, "resume_outcome", inspect_runner)
    runtime = create_runtime(settings=Settings(
        _env_file=None, runtime="custom", llm_backend="openai", runs_root=str(tmp_path),
    ))
    assert await runtime.resume("run_12345678") == ("langgraph", "FakeLLMClient")
