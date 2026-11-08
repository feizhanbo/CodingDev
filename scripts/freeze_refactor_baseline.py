"""Freeze the working source (including uncommitted files), never credentials."""

import hashlib
import json
import platform
import subprocess
import sys
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "runs" / "pre-langgraph-baseline"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "source.zip"
    if archive.exists():
        raise SystemExit("Baseline already exists; refusing to overwrite recovery evidence")
    files = set()
    for directory in ("devpilot/devpilot", "devpilot/tests", "scripts", ".github"):
        for path in (root / directory).rglob("*"):
            if path.is_file() and not any(
                part in {"__pycache__", ".pytest_cache", ".ruff_cache"}
                for part in path.parts
            ) and path.suffix not in {".pyc", ".pyo"} and not path.name.startswith(".env"):
                files.add(path)
    for name in ("pyproject.toml", "uv.lock", ".python-version", "README.md"):
        path = root / "devpilot" / name
        if path.exists():
            files.add(path)
    hashes = {}
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            name = path.relative_to(root).as_posix()
            content = path.read_bytes()
            hashes[name] = hashlib.sha256(content).hexdigest()
            bundle.writestr(name, content)
    manifest = {
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "source": "working tree, including uncommitted source",
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": hashes,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert all(hashlib.sha256(bundle.read(p)).hexdigest() == h for p, h in hashes.items())
    print(f"Verified {len(hashes)} files in {archive}")


if __name__ == "__main__":
    main()
