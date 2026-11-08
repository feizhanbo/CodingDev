"""Load tasks and build isolated runtime dependencies."""

from __future__ import annotations

from collections.abc import Callable
from importlib.resources import files
from pathlib import Path

import yaml

from devpilot.agents.developer import DeveloperAgent
from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
from devpilot.domain.task import DevelopmentTask
from devpilot.llm.base import LLMResponse
from devpilot.llm.fake import FakeLLMClient
from devpilot.llm.openai import OpenAIClient
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.contracts import RunRequest
from devpilot.runtime.custom.runner import CustomAgentRunner
from devpilot.runtime.shared.context import ContextBuilder
from devpilot.runtime.shared.lifecycle import RuntimeLifecycle
from devpilot.runtime.shared.loop_guard import LoopGuard
from devpilot.runtime.shared.state_manager import StateManager
from devpilot.settings import Settings
from devpilot.tools.code.apply_patch import ApplyPatch
from devpilot.tools.code.create_file import CreateFile
from devpilot.tools.git.diff import GitDiff
from devpilot.tools.git.status import GitStatus
from devpilot.tools.registry import ToolRegistry
from devpilot.tools.repo.list_files import ListFiles
from devpilot.tools.repo.read_file import ReadFile
from devpilot.tools.repo.search_code import SearchCode
from devpilot.tools.test.run_tests import RunTests
from devpilot.tracing import MetricsCollector, TraceWriter
from devpilot.verification import TaskVerifier
from devpilot.workspace.sandbox import SandboxWorkspace


def load_issue(path: str) -> DevelopmentTask:
    """Load a development issue from a YAML file.

    Maps YAML fields to :class:`DevelopmentTask` and records the source
    file path in ``metadata``.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Issue file not found: {path}")
    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid issue YAML (expected mapping): {path}")
    required = {"id", "title", "description", "acceptance_criteria"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"Issue YAML missing required fields: {sorted(missing)}")
    metadata = dict(data.get("metadata") or {})
    metadata["issue_file"] = str(p.resolve())
    return DevelopmentTask(
        id=data["id"],
        title=data["title"],
        description=data["description"],
        acceptance_criteria=list(data.get("acceptance_criteria", [])),
        constraints=list(data.get("constraints", [])),
        metadata=metadata,
    )


def register_all_tools(registry: ToolRegistry, settings: Settings | None = None) -> None:
    """Register all eight DevPilot tools onto *registry*."""
    registry.register(ListFiles())
    registry.register(SearchCode())
    registry.register(ReadFile())
    registry.register(ApplyPatch())
    registry.register(CreateFile())
    settings = settings or Settings()
    registry.register(
        RunTests(
            settings.test_python,
            settings.test_timeout_seconds,
            settings.runs_root,
            output_limit_bytes=settings.max_test_output_bytes,
        )
    )
    registry.register(GitDiff())
    registry.register(GitStatus())


def smoke_repository() -> str:
    return str(files("devpilot") / "fixtures" / "smoke")


def create_fake_client() -> FakeLLMClient:
    """Exercise a genuine code edit, failure, repair, added test and verification."""

    def patch(before: str, after: str) -> dict:
        return {
            "patch": "--- a/calculator.py\n+++ b/calculator.py\n@@ -4 +4 @@\n"
            f"-    return {before}\n+    return {after}\n"
        }

    actions = [
        ToolAction(tool="repo.search_code", arguments={"query": "add"}),
        ToolAction(tool="repo.read_file", arguments={"path": "calculator.py"}),
        ToolAction(tool="code.apply_patch", arguments=patch("0", "a - b")),
        ToolAction(tool="test.run", arguments={}),
        ToolAction(tool="code.apply_patch", arguments=patch("a - b", "a + b")),
        ToolAction(
            tool="code.create_file",
            arguments={
                "path": "tests/test_addition_edges.py",
                "content": (
                    "from calculator import add\n\ndef test_zero():\n    assert add(0, 9) == 9\n"
                ),
            },
        ),
        ToolAction(tool="test.run", arguments={}),
    ]
    responses = [LLMResponse(model="fake", decision=AgentDecision(action=a)) for a in actions]
    responses.append(
        LLMResponse(
            model="fake",
            decision=AgentDecision(
                finish=FinishIntent(summary="Runtime smoke: addition repaired", risk="low")
            ),
        )
    )
    return FakeLLMClient(responses)


def initialize_components(
    config: RuntimeConfig | None = None,
    fake: bool = False,
    base_repo: str | None = None,
    on_event: Callable[[str, dict], None] | None = None,
    settings: Settings | None = None,
    request: RunRequest | None = None,
) -> RuntimeLifecycle:
    """Initialize all DevPilot components and return a ready runner."""
    settings = settings or Settings()
    if request and request.policy:
        config = request.policy.config()
    if request and request.workspace_start:
        base_repo = request.workspace_start.source
    config = config or settings.runtime_config()
    settings = settings.model_copy(
        update={name: getattr(config, name) for name in config.__dataclass_fields__}
    )
    # 1. LLM Client
    if fake:
        llm_client = create_fake_client()
    elif settings.llm_backend == "langchain":
        from devpilot.llm.langchain import LangChainLLMClient

        llm_client = LangChainLLMClient(settings.llm_config())
    else:
        llm_client = OpenAIClient(config=settings.llm_config())

    # 2. Tool Registry
    registry = ToolRegistry()
    register_all_tools(registry, settings)

    # 3. Sandbox
    ws_config = settings.workspace_config()
    workspace_type = SandboxWorkspace
    workspace_options = {}
    if request and request.workspace_start and request.workspace_start.kind == "benchmark":
        from devpilot.evals.benchmark import BenchmarkWorkspace

        workspace_type = BenchmarkWorkspace
        workspace_options["issue_id"] = request.workspace_start.issue_id
    sandbox = workspace_type(
        base_repo_path=(base_repo or (smoke_repository() if fake else ws_config.base_repo)),
        workspace_root=ws_config.workspace_root,
        runs_root=ws_config.runs_root,
        **workspace_options,
    )

    sandbox.secrets = (settings.api_key,)
    sandbox.max_bytes = settings.workspace_max_bytes
    sandbox.total_max_bytes = settings.workspace_total_max_bytes
    sandbox.artifacts_max_bytes = settings.run_artifacts_max_bytes
    sandbox.artifacts_total_max_bytes = settings.runs_total_max_bytes
    test_tool = registry.get("test.run")
    test_tool.secrets = sandbox.secrets

    # 4. Runtime components
    state_manager = StateManager(config)
    context_builder = ContextBuilder(config, registry)
    loop_guard = LoopGuard(config)
    agent = DeveloperAgent(llm_client, registry)

    # 5. Verifier and tracing
    verifier = TaskVerifier(config)
    trace_writer = TraceWriter(ws_config.runs_root)
    trace_writer.secrets = sandbox.secrets
    context_builder.trace_writer = trace_writer
    metrics = MetricsCollector()

    runner_type = CustomAgentRunner
    if settings.runtime == "langgraph":
        from devpilot.runtime.langgraph.runner import LangGraphAgentRunner

        runner_type = LangGraphAgentRunner
    runner = runner_type(
        agent=agent,
        registry=registry,
        sandbox=sandbox,
        state_manager=state_manager,
        context_builder=context_builder,
        loop_guard=loop_guard,
        config=config,
        on_event=on_event,
        verifier=verifier,
        trace_writer=trace_writer,
        metrics=metrics,
    )
    runner.purpose = request.purpose if request else "ordinary"
    return runner
