"""Tests for the SandboxWorkspace."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from devpilot.workspace import SandboxWorkspace


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _make_baseline(tmp_path: Path) -> Path:
    """Create a fake baseline repo with source files and excluded dirs."""
    base = tmp_path / "baseline"
    base.mkdir()
    _write(base / "app.py", "x = 1\n")
    _write(base / "src" / "main.py", 'def hello():\n    return "world"\n')
    _write(base / "README.md", "# Baseline\n")
    # Files/dirs that should be ignored during copy
    (base / ".git").mkdir()
    _write(base / ".git" / "special_marker", "baseline-only")
    (base / ".venv").mkdir()
    _write(base / ".venv" / "lib.py", "# venv file\n")
    (base / "__pycache__").mkdir()
    _write(base / "__pycache__" / "app.cpython-314.pyc", "# pyc\n")
    _write(base / "data.db", "dbdata\n")
    return base


def _make_sandbox(tmp_path: Path, base: Path) -> SandboxWorkspace:
    return SandboxWorkspace(
        base_repo_path=str(base),
        workspace_root=str(tmp_path / "workspaces"),
        runs_root=str(tmp_path / "runs"),
    )


class TestSandboxCreate:
    def test_copies_baseline_repo(self, tmp_path: Path) -> None:
        base = _make_baseline(tmp_path)
        sandbox = _make_sandbox(tmp_path, base)
        repo_path = sandbox.create("run-1")
        repo = Path(repo_path)
        assert repo.is_dir()
        assert (repo / "app.py").read_text(encoding="utf-8") == "x = 1\n"
        assert (repo / "src" / "main.py").exists()
        assert (repo / "README.md").exists()

    def test_workspace_repo_path_is_correct(self, tmp_path: Path) -> None:
        base = _make_baseline(tmp_path)
        sandbox = _make_sandbox(tmp_path, base)
        repo_path = sandbox.create("run-2")
        assert repo_path == sandbox.get_repo_path("run-2")
        assert repo_path.endswith(str(Path("run-2", "repo")))

    def test_runs_directory_created(self, tmp_path: Path) -> None:
        base = _make_baseline(tmp_path)
        sandbox = _make_sandbox(tmp_path, base)
        sandbox.create("run-3")
        runs_dir = Path(sandbox.get_runs_dir("run-3"))
        assert runs_dir.is_dir()

    def test_metadata_json_created(self, tmp_path: Path) -> None:
        base = _make_baseline(tmp_path)
        sandbox = _make_sandbox(tmp_path, base)
        sandbox.create("run-4")
        metadata_path = Path(sandbox.get_runs_dir("run-4")) / "workspace-metadata.json"
        assert metadata_path.is_file()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["run_id"] == "run-4"
        assert "created_at" in metadata
        assert "base_repo" in metadata
        assert "workspace_path" in metadata
        assert metadata["symlinks_detected"] == []

    def test_ignores_excluded_patterns(self, tmp_path: Path) -> None:
        base = _make_baseline(tmp_path)
        sandbox = _make_sandbox(tmp_path, base)
        repo = Path(sandbox.create("run-5"))
        # .venv, __pycache__, *.db must not be copied
        assert not (repo / ".venv").exists()
        assert not (repo / "__pycache__").exists()
        assert not (repo / "data.db").exists()
        # The baseline .git/special_marker must not survive (git init
        # creates its own .git, but not this marker file).
        assert not (repo / ".git" / "special_marker").exists()

    def test_git_initialized(self, tmp_path: Path) -> None:
        base = _make_baseline(tmp_path)
        sandbox = _make_sandbox(tmp_path, base)
        repo_path = sandbox.create("run-6")
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "baseline" in result.stdout


class TestSaveArtifact:
    def test_writes_file_correctly(self, tmp_path: Path) -> None:
        base = _make_baseline(tmp_path)
        sandbox = _make_sandbox(tmp_path, base)
        sandbox.create("run-7")
        content = '{"phase": "exploring"}'
        path = sandbox.save_artifact("run-7", "state.json", content)
        artifact = Path(path)
        assert artifact.is_file()
        assert artifact.read_text(encoding="utf-8") == content
        assert artifact.parent == Path(sandbox.get_runs_dir("run-7"))

    def test_creates_nested_dirs(self, tmp_path: Path) -> None:
        base = _make_baseline(tmp_path)
        sandbox = _make_sandbox(tmp_path, base)
        sandbox.create("run-7b")
        path = sandbox.save_artifact("run-7b", "traces/trace.jsonl", '{"step": 1}')
        assert Path(path).is_file()


class TestDestroy:
    def test_removes_workspace_directory(self, tmp_path: Path) -> None:
        base = _make_baseline(tmp_path)
        ws_root = tmp_path / "workspaces"
        sandbox = _make_sandbox(tmp_path, base)
        sandbox.create("run-8")
        assert (ws_root / "run-8").exists()
        sandbox.destroy("run-8")
        assert not (ws_root / "run-8").exists()

    def test_keeps_runs_directory(self, tmp_path: Path) -> None:
        base = _make_baseline(tmp_path)
        runs_root = tmp_path / "runs"
        sandbox = _make_sandbox(tmp_path, base)
        sandbox.create("run-9")
        sandbox.save_artifact("run-9", "result.json", '{"status": "ok"}')
        sandbox.destroy("run-9")
        assert (runs_root / "run-9").exists()
        assert (runs_root / "run-9" / "result.json").is_file()
