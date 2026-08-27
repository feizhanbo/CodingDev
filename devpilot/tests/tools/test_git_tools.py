"""Tests for the git introspection tools."""

from __future__ import annotations

from pathlib import Path

from devpilot.tools.context import ToolContext
from devpilot.tools.git import GitDiff, GitStatus


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(workspace_root=workspace, run_id="git-test")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


class TestGitDiff:
    async def test_returns_diff_with_changes(
        self, git_repo: Path
    ) -> None:
        _write(git_repo / "app.py", "x = 100\ny = 2\n")
        tool = GitDiff()
        result = await tool.execute(
            GitDiff.input_model(), _ctx(str(git_repo))
        )
        assert result.success
        assert result.data["diff"] != ""
        assert "app.py" in result.data["diff"]

    async def test_no_changes_returns_empty(
        self, git_repo: Path
    ) -> None:
        tool = GitDiff()
        result = await tool.execute(
            GitDiff.input_model(), _ctx(str(git_repo))
        )
        assert result.success
        assert result.data["diff"] == ""

    async def test_diff_with_path_filter(
        self, git_repo: Path
    ) -> None:
        _write(git_repo / "app.py", "x = 100\ny = 2\n")
        _write(git_repo / "README.md", "# Changed\n")
        tool = GitDiff()
        result = await tool.execute(
            GitDiff.input_model(path="app.py"), _ctx(str(git_repo))
        )
        assert result.success
        assert "app.py" in result.data["diff"]
        assert "README.md" not in result.data["diff"]


class TestGitStatus:
    async def test_returns_porcelain_output(
        self, git_repo: Path
    ) -> None:
        _write(git_repo / "app.py", "x = 100\ny = 2\n")
        tool = GitStatus()
        result = await tool.execute(
            GitStatus.input_model(), _ctx(str(git_repo))
        )
        assert result.success
        assert "app.py" in result.data["status"]

    async def test_counts_modified_files(
        self, git_repo: Path
    ) -> None:
        _write(git_repo / "app.py", "x = 100\ny = 2\n")
        tool = GitStatus()
        result = await tool.execute(
            GitStatus.input_model(), _ctx(str(git_repo))
        )
        assert result.success
        assert result.data["modified_count"] == 1

    async def test_clean_repo_has_zero_modified(
        self, git_repo: Path
    ) -> None:
        tool = GitStatus()
        result = await tool.execute(
            GitStatus.input_model(), _ctx(str(git_repo))
        )
        assert result.success
        assert result.data["modified_count"] == 0
