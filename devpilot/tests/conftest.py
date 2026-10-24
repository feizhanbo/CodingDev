"""Shared pytest fixtures for the DevPilot test suite."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from devpilot.tools import ToolRegistry
from devpilot.tools.code import ApplyPatch, CreateFile
from devpilot.tools.git import GitDiff, GitStatus
from devpilot.tools.repo import ListFiles, ReadFile, SearchCode
from devpilot.tools.test import RunTests


def write_file(path: Path, content: str) -> None:
    """Write a UTF-8 file with LF line endings (no OS translation)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def git(repo: Path, *args: str) -> str:
    """Run a git command in *repo*, returning stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, (
        f"git {args} failed: {result.stderr}"
    )
    return result.stdout


def init_git_repo(repo: Path) -> None:
    """Initialise a git repo with sample files and an initial commit."""
    subprocess.run(
        ["git", "init"], cwd=str(repo), capture_output=True, check=True
    )
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "core.autocrlf", "false")
    git(repo, "config", "commit.gpgsign", "false")

    write_file(repo / "app.py", "x = 1\ny = 2\n")
    write_file(
        repo / "src" / "main.py",
        'def hello():\n    return "world"\n\n\n'
        'def goodbye():\n    return "bye"\n',
    )
    write_file(repo / "README.md", "# Test Repo\n")

    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")


@pytest.fixture
def workspace(tmp_path: Path) -> str:
    """Return an absolute workspace-root string (empty directory)."""
    return str(tmp_path)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with sample files; return its path."""
    init_git_repo(tmp_path)
    return tmp_path


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a minimal pytest project layout for test.run tests."""
    write_file(
        tmp_path / "test_pass.py",
        "def test_ok():\n    assert True\n",
    )
    return tmp_path


@pytest.fixture
def registry() -> ToolRegistry:
    """Return a ToolRegistry with all eight V1 tools registered."""
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


@pytest.fixture(autouse=True)
def forbid_paid_model_requests(monkeypatch):
    """Fail before transport if a test accidentally uses a real model."""
    from openai.resources.chat.completions import AsyncCompletions, Completions

    async def blocked_async(*args, **kwargs):
        raise AssertionError("Real model requests are forbidden in tests")

    def blocked(*args, **kwargs):
        raise AssertionError("Real model requests are forbidden in tests")

    monkeypatch.setattr(AsyncCompletions, "create", blocked_async)
    monkeypatch.setattr(Completions, "create", blocked)
