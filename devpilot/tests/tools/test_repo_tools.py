"""Tests for the repository exploration tools."""

from __future__ import annotations

from pathlib import Path

from devpilot.tools.context import ToolContext
from devpilot.tools.repo import ListFiles, ReadFile, SearchCode

ARROW = "\u2192"


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(workspace_root=workspace, run_id="repo-test")


class TestListFiles:
    async def test_returns_directory_structure(
        self, git_repo: Path
    ) -> None:
        tool = ListFiles()
        result = await tool.execute(
            ListFiles.input_model(path=".", depth=3), _ctx(str(git_repo))
        )
        assert result.success
        paths = [e["path"] for e in result.data["entries"]]
        assert "app.py" in paths
        assert "README.md" in paths
        assert "src" in paths

    async def test_respects_depth_limit(self, git_repo: Path) -> None:
        tool = ListFiles()
        result = await tool.execute(
            ListFiles.input_model(path=".", depth=1), _ctx(str(git_repo))
        )
        assert result.success
        paths = [e["path"] for e in result.data["entries"]]
        # depth=1 lists only top-level entries; src is a dir but its
        # children (main.py) must not appear.
        assert "src" in paths
        assert "src/main.py" not in paths

    async def test_skips_git_dir(self, git_repo: Path) -> None:
        tool = ListFiles()
        result = await tool.execute(
            ListFiles.input_model(path=".", depth=3), _ctx(str(git_repo))
        )
        assert result.success
        paths = [e["path"] for e in result.data["entries"]]
        assert not any(p.startswith(".git") for p in paths)

    async def test_rejects_outside_workspace(self, git_repo: Path) -> None:
        tool = ListFiles()
        result = await tool.execute(
            ListFiles.input_model(path="..", depth=1), _ctx(str(git_repo))
        )
        assert not result.success
        assert result.error is not None


class TestSearchCode:
    async def test_finds_matching_text(self, git_repo: Path) -> None:
        tool = SearchCode()
        result = await tool.execute(
            SearchCode.input_model(query="hello"),
            _ctx(str(git_repo)),
        )
        assert result.success
        matches = result.data["matches"]
        assert len(matches) >= 1
        hit = matches[0]
        assert "main.py" in hit["path"]
        assert hit["line"] == 1
        assert "hello" in hit["text"]

    async def test_returns_empty_for_no_matches(
        self, git_repo: Path
    ) -> None:
        tool = SearchCode()
        result = await tool.execute(
            SearchCode.input_model(query="zzz_no_such_token_zzz"),
            _ctx(str(git_repo)),
        )
        assert result.success
        assert result.data["matches"] == []
        assert result.data["truncated"] is False

    async def test_rejects_outside_workspace(self, git_repo: Path) -> None:
        tool = SearchCode()
        result = await tool.execute(
            SearchCode.input_model(query="x", path=".."),
            _ctx(str(git_repo)),
        )
        assert not result.success


class TestReadFile:
    async def test_returns_content_with_line_numbers(
        self, git_repo: Path
    ) -> None:
        tool = ReadFile()
        result = await tool.execute(
            ReadFile.input_model(path="src/main.py"),
            _ctx(str(git_repo)),
        )
        assert result.success
        content = result.data["content"]
        assert ARROW in content
        assert "def hello()" in content
        assert result.data["start_line"] == 1

    async def test_with_line_range(self, git_repo: Path) -> None:
        tool = ReadFile()
        result = await tool.execute(
            ReadFile.input_model(
                path="src/main.py", start_line=2, end_line=4
            ),
            _ctx(str(git_repo)),
        )
        assert result.success
        assert result.data["start_line"] == 2
        assert result.data["end_line"] == 4
        assert len(result.data["content"].splitlines()) == 3

    async def test_truncates_large_files(
        self, git_repo: Path
    ) -> None:
        big = git_repo / "big.py"
        big.write_text(
            "".join(f"line {i}\n" for i in range(600)),
            encoding="utf-8",
        )
        tool = ReadFile()
        result = await tool.execute(
            ReadFile.input_model(path="big.py"),
            _ctx(str(git_repo)),
        )
        assert result.success
        assert result.data["truncated"] is True
        assert "truncated" in result.data["content"].lower()

    async def test_handles_unicode(self, git_repo: Path) -> None:
        uni = git_repo / "unicode.txt"
        uni.write_text("héllo 世界\n", encoding="utf-8")
        tool = ReadFile()
        result = await tool.execute(
            ReadFile.input_model(path="unicode.txt"),
            _ctx(str(git_repo)),
        )
        assert result.success
        assert "héllo 世界" in result.data["content"]

    async def test_rejects_outside_workspace(self, git_repo: Path) -> None:
        tool = ReadFile()
        result = await tool.execute(
            ReadFile.input_model(path="../secret.txt"),
            _ctx(str(git_repo)),
        )
        assert not result.success
