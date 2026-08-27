"""Integration tests: Sandbox + Tools working together."""

from __future__ import annotations

import subprocess
from pathlib import Path

from devpilot.domain.decision import ToolAction
from devpilot.tools import ToolContext, ToolRegistry
from devpilot.tools.code import ApplyPatch, CreateFile
from devpilot.tools.git import GitDiff, GitStatus
from devpilot.tools.repo import ListFiles, ReadFile, SearchCode
from devpilot.tools.test import RunTests
from devpilot.workspace import SandboxWorkspace


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout


def _setup_baseline(base: Path) -> None:
    """Create a baseline git repo with source files and a passing test."""
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\n")
    _write(base / "src" / "main.py", 'def hello():\n    return "world"\n')
    _write(base / "test_pass.py", "def test_ok():\n    assert True\n")
    _write(base / "README.md", "# Baseline\n")
    _git(base, "init")
    _git(base, "config", "user.email", "test@example.com")
    _git(base, "config", "user.name", "Test")
    _git(base, "config", "core.autocrlf", "false")
    _git(base, "add", ".")
    _git(base, "commit", "-m", "initial")


def _full_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for tool in (
        ListFiles(),
        ReadFile(),
        SearchCode(),
        ApplyPatch(),
        CreateFile(),
        RunTests(),
        GitDiff(),
        GitStatus(),
    ):
        reg.register(tool)
    return reg


def _action(tool: str, **kwargs: object) -> ToolAction:
    return ToolAction(tool=tool, arguments=dict(kwargs))


class TestSandboxToolIntegration:
    async def test_full_workflow(self, tmp_path: Path) -> None:
        """End-to-end: create workspace, use all tools, verify, destroy."""
        # 1. Create a temp git repo as baseline.
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        # 2-3. Create SandboxWorkspace and workspace.
        sandbox = SandboxWorkspace(
            base_repo_path=str(baseline),
            workspace_root=str(tmp_path / "workspaces"),
            runs_root=str(tmp_path / "runs"),
        )
        run_id = "integration-1"
        repo_path = sandbox.create(run_id)

        # 4. Register all 8 tools.
        reg = _full_registry()

        # 5. Create ToolContext.
        ctx = ToolContext(workspace_root=repo_path, run_id=run_id)

        # 6. repo.list_files works.
        result = await reg.execute(_action("repo.list_files", path="."), ctx)
        assert result.success
        paths = [e["path"] for e in result.data["entries"]]
        assert "app.py" in paths
        assert "src" in paths

        # 7. repo.read_file works.
        result = await reg.execute(_action("repo.read_file", path="app.py"), ctx)
        assert result.success
        assert "x = 1" in result.data["content"]

        # 8. code.create_file works (modify existing tracked file).
        result = await reg.execute(
            _action("code.create_file", path="app.py", content="x = 100\n"),
            ctx,
        )
        assert result.success

        # 9. git.diff works (shows changes to the tracked file).
        result = await reg.execute(_action("git.diff"), ctx)
        assert result.success
        assert "app.py" in result.data["diff"]

        # 10. git.status works.
        result = await reg.execute(_action("git.status"), ctx)
        assert result.success
        assert result.data["modified_count"] >= 1

        # 8b. code.create_file also works for a brand-new file.
        result = await reg.execute(
            _action("code.create_file", path="new_module.py", content="z = 3\n"),
            ctx,
        )
        assert result.success
        assert Path(repo_path, "new_module.py").is_file()

        # 11. repo.search_code works.
        result = await reg.execute(
            _action("repo.search_code", query="hello"), ctx
        )
        assert result.success
        assert len(result.data["matches"]) >= 1

        # 12. test.run works.
        result = await reg.execute(
            _action("test.run", target="test_pass.py"), ctx
        )
        assert result.success
        assert result.data["passed"] == 1

        # 13. Destroy workspace.
        sandbox.destroy(run_id)

        # 14. Verify workspace is cleaned up.
        assert not Path(repo_path).exists()
        # Runs directory is preserved.
        assert Path(sandbox.get_runs_dir(run_id)).exists()

    async def test_tools_reject_outside_workspace(self, tmp_path: Path) -> None:
        """All path-validating tools reject paths outside the workspace."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        sandbox = SandboxWorkspace(
            base_repo_path=str(baseline),
            workspace_root=str(tmp_path / "workspaces"),
            runs_root=str(tmp_path / "runs"),
        )
        run_id = "integration-2"
        repo_path = sandbox.create(run_id)
        reg = _full_registry()
        ctx = ToolContext(workspace_root=repo_path, run_id=run_id)

        try:
            # repo.list_files with ../
            result = await reg.execute(
                _action("repo.list_files", path=".."), ctx
            )
            assert not result.success

            # repo.read_file with ../
            result = await reg.execute(
                _action("repo.read_file", path="../escape.txt"), ctx
            )
            assert not result.success

            # repo.search_code with ../
            result = await reg.execute(
                _action("repo.search_code", query="x", path=".."), ctx
            )
            assert not result.success

            # code.create_file with ../
            result = await reg.execute(
                _action("code.create_file", path="../escape.py", content="x"),
                ctx,
            )
            assert not result.success

            # git.diff with ../
            result = await reg.execute(_action("git.diff", path=".."), ctx)
            assert not result.success
        finally:
            sandbox.destroy(run_id)
