"""Tests for the code modification tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

from devpilot.tools.code import ApplyPatch, CreateFile
from devpilot.tools.context import ToolContext


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(workspace_root=workspace, run_id="code-test")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True
    )
    assert r.returncode == 0, f"git {args} failed: {r.stderr}"
    return r.stdout


class TestApplyPatch:
    async def test_valid_patch_modifies_file(
        self, git_repo: Path
    ) -> None:
        repo = git_repo
        app = repo / "app.py"
        # Produce a real diff, then revert before applying via the tool.
        _write(app, "x = 100\ny = 2\n")
        diff = _git(repo, "diff", "--", "app.py")
        _git(repo, "checkout", "--", "app.py")

        tool = ApplyPatch()
        result = await tool.execute(
            ApplyPatch.input_model(patch=diff), _ctx(str(repo))
        )
        assert result.success
        assert "app.py" in result.data["modified_files"]
        assert "x = 100" in app.read_text(encoding="utf-8")

    async def test_empty_patch_returns_error(
        self, git_repo: Path
    ) -> None:
        tool = ApplyPatch()
        result = await tool.execute(
            ApplyPatch.input_model(patch="   "), _ctx(str(git_repo))
        )
        assert not result.success
        assert "empty patch" in (result.error or "").lower()

    async def test_context_mismatch_returns_error(
        self, git_repo: Path
    ) -> None:
        patch = (
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-x = 999\n"
            "+x = 100\n"
            " y = 2\n"
        )
        tool = ApplyPatch()
        result = await tool.execute(
            ApplyPatch.input_model(patch=patch), _ctx(str(git_repo))
        )
        assert not result.success
        assert result.error is not None

    async def test_rejects_paths_outside_workspace(
        self, git_repo: Path
    ) -> None:
        patch = (
            "--- /dev/null\n"
            "+++ b/../../outside.py\n"
            "@@ -0,0 +1 @@\n"
            "+hello\n"
        )
        tool = ApplyPatch()
        result = await tool.execute(
            ApplyPatch.input_model(patch=patch), _ctx(str(git_repo))
        )
        assert not result.success
        assert result.data["modified_files"] == []


class TestCreateFile:
    async def test_creates_new_file(
        self, git_repo: Path
    ) -> None:
        tool = CreateFile()
        result = await tool.execute(
            CreateFile.input_model(
                path="newfile.py", content="print('hi')\n"
            ),
            _ctx(str(git_repo)),
        )
        assert result.success
        created = git_repo / "newfile.py"
        assert created.is_file()
        assert "print('hi')" in created.read_text(encoding="utf-8")

    async def test_rejects_path_outside_workspace(
        self, git_repo: Path
    ) -> None:
        tool = CreateFile()
        result = await tool.execute(
            CreateFile.input_model(
                path="../outside.py", content="x\n"
            ),
            _ctx(str(git_repo)),
        )
        assert not result.success
        assert not (git_repo.parent / "outside.py").exists()

    async def test_creates_parent_directories(
        self, git_repo: Path
    ) -> None:
        tool = CreateFile()
        result = await tool.execute(
            CreateFile.input_model(
                path="sub/deep/file.py", content="y = 1\n"
            ),
            _ctx(str(git_repo)),
        )
        assert result.success
        assert (git_repo / "sub" / "deep" / "file.py").is_file()
