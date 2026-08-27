"""Tests for the PathGuard security component."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from devpilot.tools.path_guard import PathGuard


@pytest.fixture
def guard(workspace: str) -> PathGuard:
    return PathGuard(workspace)


class TestPathGuardValid:
    def test_valid_relative_path_resolves(
        self, workspace: str, tmp_path: Path, guard: PathGuard
    ) -> None:
        (tmp_path / "hello.py").write_text("x", encoding="utf-8")
        resolved = guard.validate_path("hello.py")
        assert resolved == (tmp_path / "hello.py").resolve()

    def test_nested_relative_path(self, tmp_path: Path, guard: PathGuard) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("y", encoding="utf-8")
        resolved = guard.validate_path("src/main.py")
        assert resolved == (tmp_path / "src" / "main.py").resolve()

    def test_normal_file_inside_workspace_allowed(
        self, tmp_path: Path, guard: PathGuard
    ) -> None:
        (tmp_path / "app.py").write_text("z", encoding="utf-8")
        resolved = guard.validate_path("app.py")
        assert resolved.is_relative_to(tmp_path.resolve())


class TestPathGuardRejection:
    def test_traversal_rejected(self, guard: PathGuard) -> None:
        with pytest.raises(PermissionError, match="outside workspace"):
            guard.validate_path("../secret.txt")

    def test_absolute_path_outside_rejected(
        self, workspace: str, guard: PathGuard
    ) -> None:
        outside = str(Path(workspace).parent / "outside.txt")
        with pytest.raises(PermissionError, match="outside workspace"):
            guard.validate_path(outside)

    def test_symlink_outside_rejected(
        self, workspace: str, tmp_path: Path, guard: PathGuard
    ) -> None:
        target = tmp_path.parent / "escape_target.txt"
        target.write_text("secret", encoding="utf-8")
        link = tmp_path / "badlink"
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")
        with pytest.raises(PermissionError):
            guard.validate_path("badlink")

    def test_env_file_rejected(self, guard: PathGuard) -> None:
        with pytest.raises(PermissionError, match="forbidden"):
            guard.validate_path(".env")

    def test_env_file_in_subdir_rejected(
        self, tmp_path: Path, guard: PathGuard
    ) -> None:
        (tmp_path / "config").mkdir()
        with pytest.raises(PermissionError, match="forbidden"):
            guard.validate_path("config/.env")

    def test_git_config_rejected(self, guard: PathGuard) -> None:
        with pytest.raises(PermissionError, match="forbidden"):
            guard.validate_path(".git/config")

    def test_ssh_key_rejected(self, guard: PathGuard) -> None:
        with pytest.raises(PermissionError, match="forbidden"):
            guard.validate_path(".ssh/id_rsa")
