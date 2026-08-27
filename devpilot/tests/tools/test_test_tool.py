"""Tests for the test.run tool."""

from __future__ import annotations

from pathlib import Path

from devpilot.tools.context import ToolContext
from devpilot.tools.test import RunTests


def _ctx(workspace: str, run_id: str = "tt-test") -> ToolContext:
    return ToolContext(workspace_root=workspace, run_id=run_id)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


class TestRunTests:
    async def test_passing_tests(self, sample_project: Path) -> None:
        tool = RunTests()
        result = await tool.execute(
            RunTests.input_model(target="test_pass.py"),
            _ctx(str(sample_project)),
        )
        assert result.success
        assert result.data["exit_code"] == 0
        assert result.data["passed"] == 1

    async def test_failing_tests(self, sample_project: Path) -> None:
        _write(
            sample_project / "test_fail.py",
            "def test_bad():\n    assert False\n",
        )
        tool = RunTests()
        result = await tool.execute(
            RunTests.input_model(target="test_fail.py"),
            _ctx(str(sample_project)),
        )
        assert not result.success
        assert result.data["exit_code"] != 0
        assert result.data["failed"] == 1

    async def test_timeout(self, sample_project: Path) -> None:
        _write(
            sample_project / "test_slow.py",
            "import time\n"
            "def test_slow():\n"
            "    time.sleep(30)\n",
        )
        tool = RunTests()
        tool.timeout_seconds = 1
        result = await tool.execute(
            RunTests.input_model(target="test_slow.py"),
            _ctx(str(sample_project)),
        )
        assert not result.success
        assert result.data["exit_code"] == -1
        assert "timed out" in result.data["summary"].lower()

    async def test_saves_log_file(self, sample_project: Path) -> None:
        tool = RunTests()
        result = await tool.execute(
            RunTests.input_model(target="test_pass.py"),
            _ctx(str(sample_project)),
        )
        assert result.success
        log_file = Path(result.data["log_file"])
        assert log_file.is_file()
        assert log_file.read_text(encoding="utf-8") != ""
