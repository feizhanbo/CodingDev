"""Tests for the ToolRegistry."""

from __future__ import annotations

from pathlib import Path

import pytest

from devpilot.domain.decision import ToolAction
from devpilot.tools import ToolContext, ToolRegistry
from devpilot.tools.code import CreateFile
from devpilot.tools.repo import ListFiles, ReadFile


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(workspace_root=workspace, run_id="reg-test")


class TestRegistryRegistration:
    def test_register_and_get(self) -> None:
        reg = ToolRegistry()
        tool = ListFiles()
        reg.register(tool)
        assert reg.get("repo.list_files") is tool

    def test_duplicate_registration_raises(self) -> None:
        reg = ToolRegistry()
        reg.register(ListFiles())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(ListFiles())

    def test_get_unknown_returns_none(self) -> None:
        reg = ToolRegistry()
        assert reg.get("does.not.exist") is None


class TestRegistryExecute:
    async def test_execute_valid_action(
        self, workspace: str, tmp_path: Path
    ) -> None:
        (tmp_path / "hello.txt").write_text("hi", encoding="utf-8")
        reg = ToolRegistry()
        reg.register(ListFiles())
        action = ToolAction(
            tool="repo.list_files", arguments={"path": "."}
        )
        result = await reg.execute(action, _ctx(workspace))
        assert result.success
        paths = [e["path"] for e in result.data["entries"]]
        assert "hello.txt" in paths

    async def test_execute_unknown_tool_returns_error(
        self, workspace: str
    ) -> None:
        reg = ToolRegistry()
        action = ToolAction(tool="nope", arguments={})
        result = await reg.execute(action, _ctx(workspace))
        assert not result.success
        assert "Unknown tool" in (result.error or "")

    async def test_execute_invalid_arguments_returns_error(
        self, workspace: str
    ) -> None:
        reg = ToolRegistry()
        reg.register(ReadFile())
        # ReadFile requires "path"; omit it to trigger validation failure.
        action = ToolAction(tool="repo.read_file", arguments={})
        result = await reg.execute(action, _ctx(workspace))
        assert not result.success
        assert "Invalid arguments" in (result.error or "")

    async def test_execute_sets_duration(self, workspace: str) -> None:
        reg = ToolRegistry()
        reg.register(ListFiles())
        action = ToolAction(
            tool="repo.list_files", arguments={"path": "."}
        )
        result = await reg.execute(action, _ctx(workspace))
        assert result.success
        assert result.duration_ms is not None
        assert result.duration_ms >= 0


class TestListSchemas:
    def test_returns_correct_format(self) -> None:
        reg = ToolRegistry()
        reg.register(ListFiles())
        reg.register(CreateFile())
        schemas = reg.list_schemas()
        assert len(schemas) == 2
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            assert isinstance(schema["input_schema"], dict)
        names = [s["name"] for s in schemas]
        assert "repo.list_files" in names
        assert "code.create_file" in names
