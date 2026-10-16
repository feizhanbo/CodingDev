"""Tests for TaskVerifier."""

from __future__ import annotations

from pathlib import Path

from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools import ToolRegistry
from devpilot.tools.code import ApplyPatch, CreateFile
from devpilot.tools.git import GitDiff, GitStatus
from devpilot.tools.repo import ListFiles, ReadFile, SearchCode
from devpilot.tools.test import RunTests
from devpilot.verification import TaskVerifier
from devpilot.verification.evidence import capture_snapshot


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


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


def _make_task() -> DevelopmentTask:
    return DevelopmentTask(
        id="DEV-001",
        title="Test task",
        description="desc",
        acceptance_criteria=["c1"],
    )


def _make_state(
    modified_files: list[str] | None = None,
    run_id: str = "verifier_test",
) -> DevPilotState:
    return DevPilotState(
        run_id=run_id,
        task=_make_task(),
        phase="verifying",
        modified_files=modified_files or [],
    )


def _init_git(repo: Path) -> None:
    import subprocess

    def _git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            check=True,
        )

    _git("init")
    _git("config", "user.email", "t@e.com")
    _git("config", "user.name", "T")
    _git("config", "core.autocrlf", "false")
    _git("add", "-A")
    _git("commit", "-m", "init")
    capture_snapshot(repo, repo.parent / "artifacts")


def _make_verifier(repo: Path) -> TaskVerifier:
    verifier = TaskVerifier(RuntimeConfig())
    verifier.bind_snapshot("verifier_test", repo.parent / "artifacts" / "trusted")
    return verifier


class TestVerifySuccess:
    async def test_success_when_tests_pass_and_diff_non_empty(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo / "app.py", "x = 1\n")
        _write(repo / "test_pass.py", "def test_pass():\n    assert True\n")
        _init_git(repo)
        _write(repo / "app.py", "x = 100\n")

        verifier = _make_verifier(repo)
        state = _make_state(modified_files=["app.py"])
        result = await verifier.verify(
            _make_task(), str(repo), state, _full_registry()
        )

        assert result.success
        assert result.failure_reason is None

    async def test_result_contains_all_checks(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo / "app.py", "x = 1\n")
        _write(repo / "test_pass.py", "def test_pass():\n    assert True\n")
        _init_git(repo)
        _write(repo / "app.py", "x = 100\n")

        verifier = _make_verifier(repo)
        state = _make_state(modified_files=["app.py"])
        result = await verifier.verify(
            _make_task(), str(repo), state, _full_registry()
        )

        check_names = [c["name"] for c in result.checks]
        assert "visible_tests" in check_names
        assert "diff_non_empty" in check_names
        assert "forbidden_files" in check_names
        assert "modified_file_count" in check_names
        assert len(result.checks) == 5


class TestVerifyTestsFail:
    async def test_failure_when_tests_fail(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo / "app.py", "x = 1\n")
        _write(repo / "test_fail.py", "def test_fail():\n    assert False\n")
        _init_git(repo)
        _write(repo / "app.py", "x = 100\n")

        verifier = _make_verifier(repo)
        state = _make_state(modified_files=["app.py"])
        result = await verifier.verify(
            _make_task(), str(repo), state, _full_registry()
        )

        assert not result.success
        test_check = next(
            c for c in result.checks if c["name"] == "visible_tests"
        )
        assert not test_check["passed"]


class TestVerifyDiffEmpty:
    async def test_failure_when_diff_empty(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo / "app.py", "x = 1\n")
        _write(repo / "test_pass.py", "def test_pass():\n    assert True\n")
        _init_git(repo)

        verifier = _make_verifier(repo)
        state = _make_state(modified_files=[])
        result = await verifier.verify(
            _make_task(), str(repo), state, _full_registry()
        )

        assert not result.success
        diff_check = next(
            c for c in result.checks if c["name"] == "diff_non_empty"
        )
        assert not diff_check["passed"]


class TestVerifyForbiddenFiles:
    async def test_failure_when_forbidden_file_modified(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo / "app.py", "x = 1\n")
        _write(repo / "test_pass.py", "def test_pass():\n    assert True\n")
        _init_git(repo)
        _write(repo / "app.py", "x = 100\n")

        verifier = _make_verifier(repo)
        _write(repo / ".env", "TEST_ONLY=1\n")
        state = _make_state(modified_files=[])
        result = await verifier.verify(
            _make_task(), str(repo), state, _full_registry()
        )

        assert not result.success
        forbidden_check = next(
            c for c in result.checks if c["name"] == "forbidden_files"
        )
        assert not forbidden_check["passed"]


class TestVerifyTooManyFiles:
    async def test_failure_when_too_many_files_modified(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo / "app.py", "x = 1\n")
        _write(repo / "test_pass.py", "def test_pass():\n    assert True\n")
        _init_git(repo)
        _write(repo / "app.py", "x = 100\n")

        verifier = _make_verifier(repo)
        many_files = [f"file_{i}.py" for i in range(11)]
        for name in many_files:
            _write(repo / name, "VALUE = 1\n")
        state = _make_state(modified_files=[])
        result = await verifier.verify(
            _make_task(), str(repo), state, _full_registry()
        )

        assert not result.success
        count_check = next(
            c for c in result.checks if c["name"] == "modified_file_count"
        )
        assert not count_check["passed"]
