"""Tests verifying hidden tests are isolated from agent access.

These integration tests set up a real SandboxWorkspace from a baseline
repo and place hidden tests *outside* the baseline (mirroring the real
evals/hidden_tests layout). They confirm that none of the agent-facing
repo tools (list_files, search_code, read_file) can reach the hidden
tests, while the EvalRunner -- the legitimate evaluation harness -- can.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from devpilot.domain.state import DevPilotState, Observation
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.tools.context import ToolContext
from devpilot.tools.path_guard import PathGuard
from devpilot.tools.repo import ListFiles, ReadFile, SearchCode
from devpilot.workspace.sandbox import SandboxWorkspace

# Unique markers placed inside the hidden test file. If any agent tool
# ever returns these strings, the isolation has failed.
HIDDEN_MARKER = "DEVPILOT_HIDDEN_MARKER_ZZZ999"
HIDDEN_FUNC = "test_hidden_isolation_secret"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _make_baseline(tmp_path: Path) -> Path:
    """Create a minimal baseline repo (mirrors shopflow-order-service)."""
    base = tmp_path / "baseline"
    base.mkdir()
    _write(base / "app.py", "x = 1\n")
    _write(base / "src" / "main.py", 'def hello():\n    return "world"\n')
    _write(base / "README.md", "# Baseline\n")
    return base


def _make_hidden_tests(tmp_path: Path) -> Path:
    """Create hidden tests *outside* the baseline repo."""
    hidden_root = tmp_path / "devpilot" / "evals" / "hidden_tests"
    hidden_dir = hidden_root / "DEV-001"
    _write(
        hidden_dir / "test_hidden_dev001.py",
        '"""Hidden test with a secret marker."""\n'
        "from __future__ import annotations\n\n\n"
        f"def {HIDDEN_FUNC}():\n"
        f"    # {HIDDEN_MARKER}\n"
        "    from app import x\n"
        "    assert x == 1\n",
    )
    return hidden_root


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(workspace_root=workspace, run_id="iso-test")


@pytest.fixture
def isolated_workspace(tmp_path: Path) -> SimpleNamespace:
    """Set up baseline repo, hidden tests, and a sandbox workspace.

    Returns a namespace with:
        sandbox      -- the SandboxWorkspace instance
        run_id       -- the workspace run identifier
        repo_path    -- absolute path to the workspace repo copy
        baseline     -- path to the baseline repo (source)
        hidden_root  -- path to hidden tests dir (outside baseline)
        tmp_path     -- the temp path root
    """
    baseline = _make_baseline(tmp_path)
    hidden_root = _make_hidden_tests(tmp_path)

    sandbox = SandboxWorkspace(
        base_repo_path=str(baseline),
        workspace_root=str(tmp_path / "workspaces"),
        runs_root=str(tmp_path / "runs"),
    )
    run_id = "iso-test"
    repo_path = sandbox.create(run_id)

    return SimpleNamespace(
        sandbox=sandbox,
        run_id=run_id,
        repo_path=repo_path,
        baseline=baseline,
        hidden_root=hidden_root,
        tmp_path=tmp_path,
    )


class TestHiddenTestIsolation:
    """Verify the agent cannot access hidden tests through any repo tool."""

    # -- repo.list_files ------------------------------------------------

    async def test_list_files_cannot_access_hidden_tests(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """repo.list_files should not reveal hidden_tests directory."""
        ws = isolated_workspace
        tool = ListFiles()
        result = await tool.execute(
            ListFiles.input_model(path=".", depth=10),
            _ctx(ws.repo_path),
        )
        assert result.success
        paths = [e["path"] for e in result.data["entries"]]
        # Baseline files ARE present
        assert "app.py" in paths
        assert "src" in paths
        # Hidden tests must NOT appear
        assert not any("hidden" in p.lower() for p in paths)
        assert not any("evals" in p.lower() for p in paths)

    async def test_list_files_rejects_traversal_to_hidden_tests(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """Path traversal toward hidden_tests is rejected by PathGuard."""
        ws = isolated_workspace
        tool = ListFiles()
        result = await tool.execute(
            ListFiles.input_model(
                path="../../evals/hidden_tests/DEV-001", depth=1
            ),
            _ctx(ws.repo_path),
        )
        assert not result.success
        assert "outside workspace" in result.error

    async def test_list_files_rejects_absolute_path_to_hidden_tests(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """Absolute path to hidden_tests is rejected by PathGuard."""
        ws = isolated_workspace
        tool = ListFiles()
        result = await tool.execute(
            ListFiles.input_model(
                path=str(ws.hidden_root / "DEV-001"), depth=1
            ),
            _ctx(ws.repo_path),
        )
        assert not result.success
        assert "outside workspace" in result.error

    # -- repo.search_code -----------------------------------------------

    async def test_search_code_cannot_access_hidden_tests(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """Searching for hidden-test markers returns no matches."""
        ws = isolated_workspace
        tool = SearchCode()
        result = await tool.execute(
            SearchCode.input_model(query=HIDDEN_MARKER),
            _ctx(ws.repo_path),
        )
        assert result.success
        assert result.data["matches"] == []

    async def test_search_code_finds_no_hidden_func_in_workspace(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """The hidden test function name is not found in workspace files."""
        ws = isolated_workspace
        tool = SearchCode()
        result = await tool.execute(
            SearchCode.input_model(query=HIDDEN_FUNC),
            _ctx(ws.repo_path),
        )
        assert result.success
        assert result.data["matches"] == []

    async def test_search_code_rejects_traversal_to_hidden_tests(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """Searching with a path traversing to hidden_tests is rejected."""
        ws = isolated_workspace
        tool = SearchCode()
        result = await tool.execute(
            SearchCode.input_model(
                query="assert", path="../../evals/hidden_tests"
            ),
            _ctx(ws.repo_path),
        )
        assert not result.success

    async def test_search_code_rejects_absolute_path_to_hidden_tests(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """Searching with an absolute path to hidden_tests is rejected."""
        ws = isolated_workspace
        tool = SearchCode()
        result = await tool.execute(
            SearchCode.input_model(
                query="assert", path=str(ws.hidden_root)
            ),
            _ctx(ws.repo_path),
        )
        assert not result.success

    # -- repo.read_file -------------------------------------------------

    async def test_read_file_cannot_access_hidden_tests(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """repo.read_file rejects attempts to read hidden test files."""
        ws = isolated_workspace
        tool = ReadFile()
        result = await tool.execute(
            ReadFile.input_model(
                path="../../evals/hidden_tests/DEV-001/test_hidden_dev001.py"
            ),
            _ctx(ws.repo_path),
        )
        assert not result.success
        assert "outside workspace" in result.error

    async def test_read_file_rejects_absolute_path_to_hidden_tests(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """Absolute path to a hidden test file is rejected."""
        ws = isolated_workspace
        tool = ReadFile()
        abs_file = str(
            ws.hidden_root / "DEV-001" / "test_hidden_dev001.py"
        )
        result = await tool.execute(
            ReadFile.input_model(path=abs_file),
            _ctx(ws.repo_path),
        )
        assert not result.success
        assert "outside workspace" in result.error

    def test_read_file_rejects_path_traversal_to_hidden_tests(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """Various path-traversal variants are all rejected by PathGuard."""
        ws = isolated_workspace
        guard = PathGuard(ws.repo_path)
        attempts = [
            "../hidden_tests",
            "../../hidden_tests",
            "../../../evals/hidden_tests/DEV-001",
            "evals/../../../../hidden_tests",
            "./../../evals/hidden_tests",
        ]
        for attempt in attempts:
            with pytest.raises(PermissionError, match="outside workspace"):
                guard.validate_path(attempt)

    async def test_read_file_error_does_not_leak_hidden_content(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """Error messages must not contain hidden test file content."""
        ws = isolated_workspace
        tool = ReadFile()
        abs_file = str(
            ws.hidden_root / "DEV-001" / "test_hidden_dev001.py"
        )
        result = await tool.execute(
            ReadFile.input_model(path=abs_file),
            _ctx(ws.repo_path),
        )
        assert not result.success
        assert HIDDEN_MARKER not in (result.error or "")
        assert HIDDEN_FUNC not in (result.error or "")

    # -- Agent context ---------------------------------------------------

    async def test_context_does_not_leak_hidden_tests(
        self,
        isolated_workspace: SimpleNamespace,
        registry,  # from conftest.py -- ToolRegistry with all tools
    ) -> None:
        """Built agent context should not contain hidden test content.

        Simulates the agent attempting to access hidden tests through
        every repo tool, then builds the LLM context and verifies no
        hidden-test markers appear.
        """
        ws = isolated_workspace
        ctx = _ctx(ws.repo_path)

        # Run all three repo tools -- both legitimate (inside workspace)
        # and illegitimate (pointing at hidden tests) calls.
        lf = ListFiles()
        lf_ok = await lf.execute(
            ListFiles.input_model(path=".", depth=10), ctx
        )
        lf_bad = await lf.execute(
            ListFiles.input_model(
                path=str(ws.hidden_root / "DEV-001"), depth=5
            ),
            ctx,
        )

        sc = SearchCode()
        sc_ok = await sc.execute(
            SearchCode.input_model(query=HIDDEN_MARKER), ctx
        )
        sc_bad = await sc.execute(
            SearchCode.input_model(
                query="assert", path=str(ws.hidden_root)
            ),
            ctx,
        )

        rf = ReadFile()
        rf_bad = await rf.execute(
            ReadFile.input_model(
                path=str(
                    ws.hidden_root / "DEV-001" / "test_hidden_dev001.py"
                )
            ),
            ctx,
        )

        # Build observations from tool results (as the runtime would)
        tool_results = [
            ("repo.list_files", lf_ok),
            ("repo.list_files", lf_bad),
            ("repo.search_code", sc_ok),
            ("repo.search_code", sc_bad),
            ("repo.read_file", rf_bad),
        ]
        observations = [
            Observation(
                step_id=i,
                source="tool",
                name=name,
                success=res.success,
                summary="ok" if res.success else (res.error or "error"),
                data=res.data,
            )
            for i, (name, res) in enumerate(tool_results, start=1)
        ]

        task = DevelopmentTask(
            id="DEV-001",
            title="Test",
            description="isolation test",
            acceptance_criteria=[],
        )
        state = DevPilotState(
            run_id="iso-test",
            task=task,
            phase="exploring",
            observations=observations,
        )

        builder = ContextBuilder(RuntimeConfig(), registry)
        messages = builder.build(state, ws.repo_path)
        context_text = "\n".join(m.content for m in messages)

        assert HIDDEN_MARKER not in context_text
        assert HIDDEN_FUNC not in context_text

    # -- EvalRunner (legitimate access) ---------------------------------

    def test_hidden_tests_dir_outside_workspace(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """Hidden tests must live outside the workspace root."""
        ws = isolated_workspace
        repo = Path(ws.repo_path).resolve()
        hidden = ws.hidden_root.resolve()
        assert not hidden.is_relative_to(repo)

    async def test_eval_runner_can_access_and_run_hidden_tests(
        self, isolated_workspace: SimpleNamespace
    ) -> None:
        """EvalRunner (evaluation harness) can copy and run hidden tests.

        This is the legitimate path: hidden tests are copied into the
        workspace *after* the agent run completes, then executed.
        """
        ws = isolated_workspace
        from devpilot.evals.runner import EvalRunner

        runner = EvalRunner(
            base_repo_path=str(ws.baseline),
            hidden_tests_dir=str(ws.hidden_root),
        )
        result = runner._run_hidden_tests(
            "DEV-001", ws.run_id, ws.sandbox
        )
        assert result["passed"] is True
        assert result["pass_rate"] == 1.0

        # Evaluator can execute the hidden suite, but never injects it into the Agent repo.
        workspace_hidden = Path(ws.repo_path) / "hidden_tests"
        assert not workspace_hidden.exists()
        report = Path(result["report_file"])
        assert not report.is_relative_to(Path(ws.repo_path))
        copied = report.parent / "tests" / "test_hidden_dev001.py"
        assert HIDDEN_MARKER in copied.read_text(encoding="utf-8")
