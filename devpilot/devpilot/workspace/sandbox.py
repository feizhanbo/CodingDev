"""Workspace sandbox for isolated agent execution."""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from devpilot.security import linked, permitted_files, redact
from devpilot.storage import atomic_write

logger = logging.getLogger(__name__)

_IGNORE_PATTERNS = shutil.ignore_patterns(".git", "__pycache__", ".venv", "*.db")


class SandboxWorkspace:
    """Create and manage isolated workspace copies of the baseline repo."""

    def __init__(
        self,
        base_repo_path: str,
        workspace_root: str = "./workspaces",
        runs_root: str = "./runs",
    ) -> None:
        self.secrets: tuple[str, ...] = ()
        self.max_bytes = 268435456
        self.total_max_bytes = 2147483648
        self.base_repo = Path(base_repo_path).resolve()
        self.workspace_root = Path(workspace_root).resolve()
        self.runs_root = Path(runs_root).resolve()

    def create(self, run_id: str) -> str:
        """Create an isolated workspace from the baseline repo.

        Copies the baseline repo into ``workspaces/{run_id}/repo``
        (skipping ``.git``, ``__pycache__``, ``.venv``, ``*.db``),
        initialises a fresh git repo, and prepares ``runs/{run_id}/``
        for artifacts.

        Returns the workspace repo path.
        """
        # 1. Prepare the workspace parent directory.
        workspace_repo = self.workspace_root / run_id / "repo"
        workspace_repo.parent.mkdir(parents=True, exist_ok=True)

        # Enumerate before copying; reject links and never copy credentials.
        sources = permitted_files(self.base_repo, self.base_repo)
        self.check_capacity(sum(p.stat().st_size for p in sources))
        symlinks = []
        workspace_repo.mkdir()
        for source in sources:
            if source.name.endswith((".db", ".pyc", ".pyo")):
                continue
            target = workspace_repo / source.relative_to(self.base_repo)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

        # 3. Initialize a fresh git repo in the workspace.
        _git_init(workspace_repo)

        # 4. Create runs/{run_id}/ directory for artifacts.
        runs_dir = self.runs_root / run_id
        runs_dir.mkdir(parents=True, exist_ok=True)

        # 5. Write workspace-metadata.json.
        metadata = {
            "run_id": run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "base_repo": str(self.base_repo),
            "workspace_path": str(workspace_repo),
            "symlinks_detected": symlinks,
        }
        (runs_dir / "workspace-metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        # 7. Return the workspace repo path.
        return str(workspace_repo)

    def check_capacity(self, source_bytes: int) -> None:
        if source_bytes > self.max_bytes:
            raise OSError("Workspace exceeds workspace_max_bytes")
        if self.workspace_root.exists():
            used = sum(
                p.stat().st_size for p in permitted_files(self.workspace_root, self.workspace_root)
            )
            if used + source_bytes > self.total_max_bytes:
                raise OSError("Workspaces exceed workspace_total_max_bytes; archive manually")

    def get_repo_path(self, run_id: str) -> str:
        """Return the workspace repo path for a run."""
        return str(self.workspace_root / run_id / "repo")

    def get_runs_dir(self, run_id: str) -> str:
        """Return the runs directory path for a run."""
        return str(self.runs_root / run_id)

    def save_artifact(self, run_id: str, name: str, content: str) -> str:
        """Save an artifact file to ``runs/{run_id}/{name}``.

        Used for ``state.json``, ``trace.jsonl``, ``result.json``,
        ``final.diff``, ``test-output.log``.

        Returns the file path.
        """
        artifact_path = self.runs_root / run_id / name
        if not artifact_path.resolve().is_relative_to(self.runs_root):
            raise PermissionError("Artifact escapes runs root")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        safe = content if artifact_path.suffix == ".diff" else redact(content, self.secrets)
        atomic_write(artifact_path, safe)
        return str(artifact_path)

    def destroy(self, run_id: str) -> None:
        """Remove ``workspaces/{run_id}/`` but keep ``runs/{run_id}/``.

        The runs directory is preserved for post-run inspection.
        """
        workspace_dir = self.workspace_root / run_id
        if (
            workspace_dir.resolve().parent != self.workspace_root
            or workspace_dir.resolve() == self.workspace_root
            or linked(workspace_dir)
        ):
            raise PermissionError("Unsafe workspace removal target")
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, onexc=_on_rmtree_error)


def _on_rmtree_error(function, path, exc) -> None:
    """Make read-only files writable and retry (Windows git objects)."""
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        return
    try:
        function(path)
    except OSError:
        return


def _detect_symlinks(base: Path) -> list[str]:
    """Return baseline-relative paths of symlinks in the baseline repo."""
    symlinks: list[str] = []
    skip_dirs = {".git", "__pycache__", ".venv"}
    for dirpath, dirnames, filenames in os.walk(base):
        # Prune ignored directories so we don't traverse into .git etc.
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in dirnames + filenames:
            full = Path(dirpath) / name
            if full.is_symlink():
                try:
                    rel = full.relative_to(base)
                    symlinks.append(str(rel))
                except ValueError:
                    symlinks.append(str(full))
    return symlinks


def _git_init(repo_path: Path) -> None:
    """Initialize a fresh git repo and commit all files as baseline."""
    _git(repo_path, "init")
    _git(repo_path, "config", "user.email", "devpilot@example.com")
    _git(repo_path, "config", "user.name", "DevPilot")
    _git(repo_path, "config", "core.autocrlf", "false")
    _git(repo_path, "config", "commit.gpgsign", "false")
    _git(repo_path, "add", "-A")
    _git(repo_path, "commit", "-m", "baseline")


def _git(repo: Path, *args: str) -> str:
    """Run a git command in *repo*, returning stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args} failed in {repo}: {result.stderr.strip()}")
    return result.stdout
