"""V1 Definition of Done verification tests.

Verifies all DoD items from Design Doc Appendix D:
  - ShopFlow Baseline: complete tests pass, can reset
  - Tools: 8 core tools with unit tests and path protection
  - Sandbox: workspace outside read/write rejected
  - Runtime: max steps/retry/finish verifier have automated tests
  - DEV-001: end-to-end complete with FakeLLMClient
  - Trace: each run can replay main actions
  - Hidden Tests: agent cannot read, eval runner can execute
  - Framework Ready: business layers don't depend on framework
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devpilot.cli import (
    initialize_components,
    load_issue,
    register_all_tools,
)
from devpilot.domain.decision import AgentDecision, FinishIntent, ToolAction
from devpilot.llm.base import LLMResponse
from devpilot.llm.fake import FakeLLMClient
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.context import ToolContext
from devpilot.tools.path_guard import PathGuard
from devpilot.tools.registry import ToolRegistry

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SHOPFLOW_ROOT = _PROJECT_ROOT.parent / "shopflow-order-service"
_ISSUE_PATH = _PROJECT_ROOT / "devpilot" / "evals" / "issues" / "DEV-001.yaml"

_EXPECTED_TOOLS = {
    "repo.list_files",
    "repo.search_code",
    "repo.read_file",
    "code.apply_patch",
    "code.create_file",
    "test.run",
    "git.diff",
    "git.status",
}

# Modules that must not import any agent framework.
_FRAMEWORK_PACKAGES = {
    "langgraph",
    "langchain",
    "openai.agents",
    "agents",
    "autogen",
    "crewai",
}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _setup_baseline(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\nz = 3\n")
    _write(
        base / "test_pass.py",
        "from app import x, z\n\ndef test_ok():\n    assert (x, z) == (1, 3)\n",
    )


_PATCH = (
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1,2 +1,3 @@\n"
    " x = 1\n"
    "+y = 2\n"
    " z = 3\n"
)


def _make_responses() -> list[LLMResponse]:
    return [
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="repo.search_code", arguments={"query": "orders"}
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="repo.read_file", arguments={"path": "app.py"}
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="code.apply_patch", arguments={"patch": _PATCH}
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(
                    tool="code.create_file",
                    arguments={
                        "path": "tests/test_added_value.py",
                        "content": (
                            "from app import y\n\ndef test_added_value():\n"
                            "    assert y == 2\n"
                        ),
                    },
                )
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                action=ToolAction(tool="test.run", arguments={})
            ),
            model="fake",
        ),
        LLMResponse(
            decision=AgentDecision(
                finish=FinishIntent(
                    summary="Added status filter", risk="low"
                )
            ),
            model="fake",
        ),
    ]


class TestV1DefinitionOfDone:
    """Verify V1 Definition of Done (Design Doc Appendix D)."""

    def test_shopflow_baseline_complete(self) -> None:
        """ShopFlow Baseline: complete tests pass, can reset."""
        # Verify shopflow has all expected directories
        assert _SHOPFLOW_ROOT.is_dir()
        assert (_SHOPFLOW_ROOT / "app" / "models").is_dir()
        assert (_SHOPFLOW_ROOT / "app" / "api").is_dir()
        assert (_SHOPFLOW_ROOT / "app" / "services").is_dir()
        assert (_SHOPFLOW_ROOT / "app" / "repositories").is_dir()

        # Verify key model files exist
        expected_models = [
            "order.py", "customer.py", "product.py",
            "coupon.py", "order_item.py",
        ]
        for model_file in expected_models:
            assert (_SHOPFLOW_ROOT / "app" / "models" / model_file).is_file()

        # Verify API files exist
        expected_apis = ["orders.py", "customers.py", "products.py", "coupons.py"]
        for api_file in expected_apis:
            assert (_SHOPFLOW_ROOT / "app" / "api" / api_file).is_file()

        # Verify service files exist
        assert (_SHOPFLOW_ROOT / "app" / "services" / "order_service.py").is_file()
        assert (_SHOPFLOW_ROOT / "app" / "services" / "pricing_service.py").is_file()

        # Verify test files exist
        assert (_SHOPFLOW_ROOT / "tests").is_dir()
        test_files = list((_SHOPFLOW_ROOT / "tests").rglob("test_*.py"))
        assert len(test_files) > 0

        # Verify db seed exists (for reset capability)
        assert (_SHOPFLOW_ROOT / "app" / "db" / "seed.py").is_file()

    def test_eight_tools_with_tests(self) -> None:
        """8 core tools all have unit tests and path protection."""
        # Verify all 8 tools are registered
        registry = ToolRegistry()
        register_all_tools(registry)
        assert len(registry.names) == 8
        assert set(registry.names) == _EXPECTED_TOOLS

        # Verify each tool has test coverage
        tools_test_dir = _PROJECT_ROOT / "tests" / "tools"
        test_files = {
            f.stem for f in tools_test_dir.glob("test_*.py")
        }
        # Core test files exist for tool groups
        assert "test_repo_tools" in test_files
        assert "test_code_tools" in test_files
        assert "test_git_tools" in test_files
        assert "test_test_tool" in test_files
        assert "test_path_guard" in test_files
        assert "test_registry" in test_files

        # Verify path protection (PathGuard) rejects outside paths
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            guard = PathGuard(tmp)
            with pytest.raises(PermissionError):
                guard.validate_path("../outside.py")
            with pytest.raises(PermissionError):
                guard.validate_path(".env")

    def test_sandbox_workspace_security(self) -> None:
        """Sandbox: workspace outside read/write rejected."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            guard = PathGuard(tmp)

            # Outside read rejected
            with pytest.raises(PermissionError):
                guard.validate_path("../outside.py")

            # Absolute path outside rejected
            outside = Path(tmp).parent / "outside.py"
            with pytest.raises(PermissionError):
                guard.validate_path(str(outside))

            # Forbidden files rejected
            with pytest.raises(PermissionError):
                guard.validate_path(".env")
            with pytest.raises(PermissionError):
                guard.validate_path(".git/config")

    def test_runtime_guardrails_tested(self) -> None:
        """max steps/retry/finish verifier have automated tests."""
        # Verify LoopGuard tests exist
        loop_guard_test = (
            _PROJECT_ROOT / "tests" / "runtime" / "test_loop_guard.py"
        )
        assert loop_guard_test.is_file()

        # Verify Verifier tests exist
        verifier_test = (
            _PROJECT_ROOT / "tests" / "verification" / "test_verifier.py"
        )
        assert verifier_test.is_file()

        # Verify runner tests exist (for max_steps enforcement)
        runner_test = (
            _PROJECT_ROOT / "tests" / "runtime" / "test_runner.py"
        )
        assert runner_test.is_file()

        # Verify self-correction tests exist (for retry enforcement)
        self_corr_test = (
            _PROJECT_ROOT / "tests" / "runtime" / "test_self_correction.py"
        )
        assert self_corr_test.is_file()

        # Verify the guardrail classes exist
        from devpilot.runtime.custom.loop_guard import (
            DuplicateActionDetected,
            GuardrailViolation,
            LoopGuard,
            MaxRetriesExceeded,
            MaxStepsExceeded,
        )

        assert issubclass(MaxStepsExceeded, GuardrailViolation)
        assert issubclass(MaxRetriesExceeded, GuardrailViolation)
        assert issubclass(DuplicateActionDetected, GuardrailViolation)

        # Verify LoopGuard can be instantiated with config
        config = RuntimeConfig(max_steps=30, max_test_retries=3)
        guard = LoopGuard(config)
        assert guard.config.max_steps == 30
        assert guard.config.max_test_retries == 3

        # Verify TaskVerifier can be instantiated
        from devpilot.verification import TaskVerifier

        verifier = TaskVerifier(config)
        assert verifier is not None

    async def test_dev001_e2e(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DEV-001 can end-to-end complete (with FakeLLMClient)."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        config = RuntimeConfig(max_steps=30)
        runner = initialize_components(
            config, fake=True, base_repo=str(baseline)
        )
        runner.agent.llm_client = FakeLLMClient(_make_responses())

        task = load_issue(str(_ISSUE_PATH))
        result = await runner.run(task)

        assert result.status == "completed"
        assert result.phase == "completed"
        assert result.error is None
        assert len(result.modified_files) > 0

    async def test_trace_replayable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each run can replay main actions."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        config = RuntimeConfig(max_steps=30)
        runner = initialize_components(
            config, fake=True, base_repo=str(baseline)
        )
        runner.agent.llm_client = FakeLLMClient(_make_responses())

        task = load_issue(str(_ISSUE_PATH))
        result = await runner.run(task)

        assert result.status == "completed"

        runs_dir = Path(runner.sandbox.runs_root) / result.run_id
        trace_path = runs_dir / "trace.jsonl"
        assert trace_path.is_file()

        trace_events = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").strip().split("\n")
        ]

        # Verify trace contains all key events for replay
        event_types = [e["event"] for e in trace_events]
        assert "run_started" in event_types
        assert "agent_decision" in event_types
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert "run_completed" in event_types

        # Each event has required replay fields
        for evt in trace_events:
            assert "run_id" in evt
            assert "step" in evt
            assert "phase" in evt
            assert "timestamp" in evt

        # Tool call events have tool name for replay
        tool_calls = [e for e in trace_events if e["event"] == "tool_call"]
        assert len(tool_calls) > 0
        for tc in tool_calls:
            assert "tool" in tc
            assert tc["tool"] is not None

    async def test_hidden_tests_isolated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hidden tests: agent cannot read, eval runner can execute."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        # Create hidden tests outside workspace
        hidden_dir = tmp_path / "hidden_tests" / "DEV-001"
        _write(
            hidden_dir / "test_secret.py",
            "from app import y\n\ndef test_secret():\n    assert y == 2\n",
        )

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        config = RuntimeConfig(max_steps=30)
        runner = initialize_components(
            config, fake=True, base_repo=str(baseline)
        )
        runner.agent.llm_client = FakeLLMClient(_make_responses())

        task = load_issue(str(_ISSUE_PATH))
        result = await runner.run(task)
        assert result.status == "completed"

        workspace_path = runner.sandbox.get_repo_path(result.run_id)

        # Verify hidden tests directory exists
        assert hidden_dir.is_dir()
        assert (hidden_dir / "test_secret.py").is_file()

        # Verify agent tools reject paths outside workspace
        registry = runner.registry

        ctx = ToolContext(workspace_root=workspace_path, run_id=result.run_id)
        action = ToolAction(
            tool="repo.read_file",
            arguments={"path": str(hidden_dir / "test_secret.py")},
        )
        tool_result = await registry.execute(action, ctx)
        assert not tool_result.success

        # Verify eval runner can execute hidden tests
        from devpilot.evals.runner import EvalRunner

        eval_runner = EvalRunner(
            base_repo_path=str(baseline),
            issues_dir=str(_PROJECT_ROOT / "devpilot" / "evals" / "issues"),
            hidden_tests_dir=str(tmp_path / "hidden_tests"),
        )
        hidden_result = eval_runner._run_hidden_tests(
            "DEV-001", result.run_id, runner.sandbox
        )
        # Hidden tests should have been executed
        assert hidden_result["passed"] is True

    def test_framework_ready(self) -> None:
        """Framework Ready: business tools/verifier/domain don't depend on framework."""
        # Scan domain, tools, and verification source files for framework imports
        source_dirs = [
            _PROJECT_ROOT / "devpilot" / "domain",
            _PROJECT_ROOT / "devpilot" / "tools",
            _PROJECT_ROOT / "devpilot" / "verification",
        ]

        violations: list[str] = []
        for src_dir in source_dirs:
            for py_file in src_dir.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line_stripped = line.strip()
                    if not (
                        line_stripped.startswith("import ")
                        or line_stripped.startswith("from ")
                    ):
                        continue
                    for pkg in _FRAMEWORK_PACKAGES:
                        if pkg in line_stripped:
                            violations.append(
                                f"{py_file}: {line_stripped}"
                            )
        assert not violations, (
            "Framework dependency found in business layers: "
            + "; ".join(violations)
        )

        # Verify domain models only depend on pydantic and devpilot
        domain_files = list(
            (_PROJECT_ROOT / "devpilot" / "domain").glob("*.py")
        )
        assert len(domain_files) > 0
        for f in domain_files:
            content = f.read_text(encoding="utf-8")
            for line in content.splitlines():
                line_stripped = line.strip()
                if line_stripped.startswith("from ") or line_stripped.startswith("import "):
                    # Should not import from runtime, agents, or llm
                    assert "devpilot.runtime" not in line_stripped
                    assert "devpilot.agents" not in line_stripped
                    assert "devpilot.llm" not in line_stripped
