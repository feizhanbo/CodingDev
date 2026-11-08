"""Application runtime adapter; constructs fresh service dependencies per execution."""

from pathlib import Path

from devpilot.runtime.contracts import RunOutcome, RunRequest
from devpilot.runtime.manifest import read_legacy_checkpoint, read_manifest
from devpilot.workspace.sandbox import SandboxWorkspace


class ApplicationRuntime:
    def __init__(self, factory=None, **options):
        self.factory = factory
        self.options = options

    def _build(self, request=None, **overrides):
        from devpilot.application.bootstrap import initialize_components

        factory = self.factory or initialize_components
        return factory(request=request, **{**self.options, **overrides})

    async def execute(self, request: RunRequest) -> RunOutcome:
        runner = self._build(request)
        return await runner.run_outcome(request.task)

    async def resume(self, run_id: str) -> RunOutcome:
        from devpilot.settings import Settings

        settings = self.options.get("settings") or Settings()
        manifest = read_manifest(settings.runs_root, run_id)
        overrides = {}
        if manifest is not None:
            if manifest.llm_backend == "custom" and self.factory is None:
                raise ValueError("Custom model adapter requires its original runtime factory")
            update = {"runtime": manifest.runtime}
            if manifest.llm_backend in {"openai", "langchain"}:
                update["llm_backend"] = manifest.llm_backend
            overrides = {"settings": settings.model_copy(update=update),
                         "fake": manifest.llm_backend == "fake"}
        elif read_legacy_checkpoint(settings.runs_root, run_id) is not None:
            # Before manifests existed the shipped runtime was custom/OpenAI.
            # Original identity, provider and budget checks still run under its lock.
            overrides = {"settings": settings.model_copy(update={
                "runtime": "custom", "llm_backend": "openai",
            })}
        runner = self._build(**overrides)
        return await runner.resume_outcome(run_id)


# Preserve imports from the custom-first release while both engines share this
# application boundary. Engine selection remains in bootstrap and the manifest.
CustomRuntime = ApplicationRuntime


def artifact_store(outcome, settings, config):
    """Reopen artifact references without accessing runtime implementation state."""
    store = SandboxWorkspace(
        outcome.workspace,
        workspace_root=str(Path(outcome.workspace).parent.parent),
        runs_root=str(Path(outcome.artifacts).parent),
    )
    store.secrets = (settings.api_key,)
    store.artifacts_max_bytes = settings.run_artifacts_max_bytes
    store.artifacts_total_max_bytes = settings.runs_total_max_bytes
    store.diagnostic_reserve_bytes = config.diagnostic_reserve_bytes
    return store
