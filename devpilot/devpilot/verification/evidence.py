"""Frozen test evidence and filesystem-derived change accounting.

Snapshots belong to the host evaluator, outside the candidate workspace. They
protect against test editing, not arbitrary hostile code on the same host.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

CONFIG_NAMES = {
    "conftest.py",
    "pytest.ini",
    ".pytest.ini",
    "pyproject.toml",
    "tox.ini",
    "setup.cfg",
}
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "runs", "workspaces"}


def is_test(path: str) -> bool:
    p = Path(path)
    return p.suffix == ".py" and (p.name.startswith("test_") or p.name.endswith("_test.py"))


def protected(path: str) -> bool:
    p = Path(path)
    return is_test(path) or p.name in CONFIG_NAMES or "tests" in p.parts


def inventory(root: Path) -> dict[str, str]:
    hashes = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in dirs + names:
            path = Path(directory) / name
            if path.is_symlink() or path.is_junction():
                raise PermissionError(
                    f"Linked workspace path is not permitted: {path.relative_to(root)}"
                )
        for name in names:
            if name.endswith((".pyc", ".pyo", ".db", ".db-journal")):
                continue
            path = Path(directory) / name
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return hashes


def capture_snapshot(repo: Path, artifacts: Path) -> Path:
    destination = artifacts / "trusted"
    destination.mkdir(parents=True, exist_ok=False)
    hashes = inventory(repo)
    for relative in hashes:
        target = destination / "baseline" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / relative, target)
    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": hashes,
                "protected": [p for p in hashes if protected(p)],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return destination


def read_manifest(trusted: Path) -> dict:
    return json.loads((trusted / "manifest.json").read_text(encoding="utf-8"))


def validate_write(repo: Path, relative: str, trusted: str | None) -> None:
    path = Path(relative)
    if path.name.lower() in CONFIG_NAMES:
        raise PermissionError(f"Protected test configuration: {relative}")
    if not trusted and (repo / relative).exists() and protected(relative):
        raise PermissionError(f"Protected existing test: {relative}")
    if trusted:
        manifest = read_manifest(Path(trusted))
        keys = {os.path.normcase(p) for p in manifest["protected"]}
        normalized = os.path.normcase(
            (repo / relative).resolve().relative_to(repo.resolve()).as_posix()
        )
        if normalized in keys:
            raise PermissionError(f"Protected baseline test: {relative}")


def check_integrity(repo: Path, trusted: Path) -> tuple[dict, list[str], list[str]]:
    manifest = read_manifest(trusted)
    original = manifest["files"]
    # Check that the evaluator's own snapshot has not drifted either.
    if inventory(trusted / "baseline") != original:
        raise PermissionError("Trusted baseline snapshot changed")
    current = inventory(repo)
    changed = sorted(
        p for p in current.keys() | original.keys() if current.get(p) != original.get(p)
    )
    violations = [p for p in changed if p in manifest["protected"] or Path(p).name in CONFIG_NAMES]
    return current, changed, violations


def materialize_candidate(
    repo: Path, trusted: Path, artifacts: Path
) -> tuple[Path, str, list[str]]:
    current, changed, violations = check_integrity(repo, trusted)
    if violations:
        raise PermissionError(f"Protected tests/configuration changed: {', '.join(violations)}")
    root = artifacts / f"verification-{uuid.uuid4().hex}"
    a, b = root / "a", root / "b"
    shutil.copytree(trusted / "baseline", a)
    b.mkdir()
    for relative in current:
        target = b / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / relative, target)
    process = subprocess.run(
        [
            "git",
            "diff",
            "--no-index",
            "--binary",
            "--no-color",
            "--src-prefix=",
            "--dst-prefix=",
            "--",
            "a",
            "b",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode not in (0, 1):
        raise RuntimeError(f"Cannot export candidate diff: {process.stderr}")
    return b, process.stdout, changed
