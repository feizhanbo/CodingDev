"""Install and check the built wheel from a directory outside the source tree."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--wheel", type=Path)
parser.add_argument("--allow-download", action="store_true",
                    help="Allow fetching the exact locked dependencies missing from cache")
args = parser.parse_args()
wheels = [args.wheel.resolve()] if args.wheel else list(
    (repo / "devpilot" / "dist").glob("devpilot-*.whl")
)
if len(wheels) != 1 or not wheels[0].is_file():
    parser.error("Select exactly one built wheel with --wheel")
wheel = wheels[0]
with tempfile.TemporaryDirectory(prefix="devpilot-wheel-") as tmp:
    root = Path(tmp)
    env = root / "venv"
    requirements = root / "locked-requirements.txt"
    subprocess.run([
        "uv", "export", "--project", str(repo / "devpilot"), "--frozen", "--offline",
        "--no-dev", "--no-emit-project", "--no-hashes", "--output-file", str(requirements),
    ], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["uv", "venv", "--offline", str(env), "--python", "3.12"], check=True)
    python = env / ("Scripts/python.exe" if __import__("os").name == "nt" else "bin/python")
    offline = [] if args.allow_download else ["--offline"]
    subprocess.run(["uv", "pip", "install", *offline, "--python", str(python),
                    "-r", str(requirements), str(wheel)], check=True)
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
from devpilot.evals.benchmark import load_manifest, verify_resources, packaged_baseline, prepare_task
assert len(load_manifest()['issues']) == 8
for issue in load_manifest()['issues']:
    verify_resources(issue)
assert len(load_manifest()["baseline_files"]) == 44
prepare_task(packaged_baseline(), Path.cwd() / "candidate", "DEV-007")
result = CliRunner().invoke(app, ['eval', '--help'])
assert result.exit_code == 0, result.output
result = CliRunner().invoke(app, ['resume', '--help'])
assert result.exit_code == 0, result.output
from devpilot.processes import run_process
from devpilot.security import process_environment
from devpilot.storage import RunLock
import sys
with RunLock(Path.cwd() / 'installed-run.lock'):
    process = run_process([sys.executable, '-c', "print('installed-process-ok')"],
        cwd=Path.cwd(), env=process_environment(), log=Path.cwd() / 'process.log', timeout=10)
assert process.exit_code == 0
assert 'installed-process-ok' in (Path.cwd() / 'process.log').read_text()
import asyncio
import json
from devpilot.application.factory import create_runtime
from devpilot.application.bootstrap import initialize_components
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.contracts import RunRequest
from devpilot.settings import Settings

class InterruptedBeforePublication(BaseException):
    pass

def interrupted_graph(**options):
    runner = initialize_components(**options)
    def interrupt(*args):
        raise InterruptedBeforePublication()
    runner._publish_terminal = interrupt
    return runner

async def verify_runtimes():
    contracts = []
    for backend in ('custom', 'langgraph'):
        settings = Settings(_env_file=None, runtime=backend,
            test_python=sys.executable,
            workspace_root=str(Path.cwd() / backend / 'workspaces'),
            runs_root=str(Path.cwd() / backend / 'runs'))
        request = RunRequest(
            DevelopmentTask(id='WHEEL', title='Fix addition', description='Fix addition',
                acceptance_criteria=['Addition is correct', 'Add tests']))
        if backend == 'langgraph':
            runtime = create_runtime(settings=settings, fake=True, factory=interrupted_graph)
            try:
                await runtime.execute(request)
            except InterruptedBeforePublication:
                pass
            else:
                raise AssertionError('Expected interruption before terminal publication')
            directories = list(Path(settings.runs_root).glob('run_*'))
            assert len(directories) == 1
            directory = directories[0]
            assert not (directory / 'result.json').exists()
            # A fresh application with conflicting defaults must use the recorded
            # graph/Fake backends. No test helpers or original service instances.
            fallback = settings.model_copy(update={'runtime': 'custom', 'llm_backend': 'openai'})
            outcome = await create_runtime(settings=fallback, fake=False).resume(directory.name)
        else:
            outcome = await create_runtime(settings=settings, fake=True).execute(request)
        result = outcome.result
        assert result.status == 'completed', result.model_dump_json()
        assert result.total_steps == 7
        assert result.budget['llm_requests'] == 8
        manifest = json.loads((Path(outcome.artifacts) / 'run-manifest.json').read_text())
        assert manifest['runtime'] == backend and manifest['llm_backend'] == 'fake'
        if backend == 'langgraph':
            assert (Path(outcome.artifacts) / 'graph.sqlite').is_file()
        contracts.append((result.total_steps, result.budget['llm_requests'],
                          [o.name for o in result.observations], outcome.final_diff))
    assert contracts[0] == contracts[1]

asyncio.run(verify_runtimes())
print('Installed wheel CLI, resources, both runtime contracts and graph resume verified')
"""
    subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
