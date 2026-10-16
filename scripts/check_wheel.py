"""Install and check the built wheel from a directory outside the source tree."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
wheel = next((repo / "devpilot" / "dist").glob("devpilot-*.whl"))
with tempfile.TemporaryDirectory(prefix="devpilot-wheel-") as tmp:
    root = Path(tmp)
    env = root / "venv"
    subprocess.run(["uv", "venv", str(env), "--python", "3.12"], check=True)
    python = env / ("Scripts/python.exe" if __import__("os").name == "nt" else "bin/python")
    subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheel)], check=True)
    code = """
from pathlib import Path
import devpilot
from devpilot.evals.runner import EvalRunner
from typer.testing import CliRunner
from devpilot.cli import app
assert Path(devpilot.__file__).is_relative_to(Path.cwd() / 'venv')
r = EvalRunner('.')
assert len(list(r.issues_dir.glob('DEV-*.yaml'))) == 8
assert (r.hidden_tests_dir / 'DEV-002' / 'test_hidden_dev002.py').is_file()
from devpilot.evals.benchmark import load_manifest, verify_resources
assert len(load_manifest()['issues']) == 8
for issue in load_manifest()['issues']:
    verify_resources(issue)
result = CliRunner().invoke(app, ['eval', '--help'])
assert result.exit_code == 0, result.output
print('Installed wheel CLI and evaluation resources verified')
"""
    subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
