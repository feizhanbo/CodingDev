import ast
import shutil
import threading
import time
import uuid
from pathlib import Path

from devpilot.execution import copy_file
from devpilot.processes import run_process
from devpilot.security import process_environment
from devpilot.storage import ArtifactQuotaExceeded
from devpilot.testing.junit import SuiteResult, parse_junit


def has_behavior_assertions(suite: Path) -> bool:
    """Reject empty/vacuous placeholder suites; this is not a semantic test judge."""
    for path in suite.rglob("*.py"):
        if path.name in {"conftest.py", "__init__.py"}:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeError):
            # Let pytest diagnose malformed suites as infrastructure errors.
            return True
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert) and any(
                isinstance(part, (ast.Name, ast.Call, ast.Attribute, ast.Subscript))
                for part in ast.walk(node.test)
            ):
                return True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"raises", "fail"}
            ):
                return True
    return False


def run_independent_suite(
    candidate: Path,
    tests_source: Path,
    artifacts: Path,
    python: str,
    *,
    timeout: int = 120,
    performance: bool = False,
    trusted_fixtures: bool = False,
    fixtures_path: Path | None = None,
    deadline: float | None = None,
    output_limit: int = 2097152,
    secrets: tuple[str, ...] = (),
    cancel: threading.Event | None = None,
) -> SuiteResult:
    """Execute evaluator tests with explicit config outside the candidate tree.

    This prevents candidate pytest config/conftest from controlling collection.
    It is process hygiene for a controlled repository, not OS-level isolation.
    """
    if cancel is not None and cancel.is_set():
        return SuiteResult(status="ERROR", reason="Suite cancelled")
    if deadline is not None and time.monotonic() >= deadline:
        return SuiteResult(status="ERROR", reason="Run deadline exceeded")
    artifacts.mkdir(parents=True, exist_ok=True)
    harness = artifacts / f"harness-{uuid.uuid4().hex}"
    suite = harness / "tests"
    if not tests_source.is_dir() or not list(tests_source.rglob("test_*.py")):
        return SuiteResult(status="NOT_EVALUATED", reason="No test suite")
    shutil.copytree(
        tests_source,
        suite,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
        copy_function=copy_file,
    )
    if trusted_fixtures:
        if fixtures_path is None:
            raise ValueError("Explicit trusted fixtures_path required")
        shutil.copyfile(fixtures_path, suite / "conftest.py")
    config = harness / "pytest.ini"
    config.write_text(
        "[pytest]\nmarkers =\n    performance: hardware dependent latency gate\n"
        "junit_family = xunit1\n",
        encoding="utf-8",
    )
    report = harness / "report.xml"
    log = harness / "output.log"
    command = [
        python,
        "-m",
        "pytest",
        str(suite),
        "-c",
        str(config),
        "--confcutdir",
        str(suite),
        "--import-mode=importlib",
        "-p",
        "no:cacheprovider",
        "-q",
        "--tb=short",
        f"--junitxml={report}",
        "-m",
        "performance" if performance else "not performance",
    ]
    # Explicit paths; do not inherit PYTEST_ADDOPTS or arbitrary PYTHONPATH/plugins.
    env = process_environment()
    env.update(
        PYTHONPATH=str(candidate.resolve()),
        PYTHONUTF8="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONNOUSERSITE="1",
        HOME=str(harness),
        USERPROFILE=str(harness),
    )
    started = time.monotonic()
    if deadline is not None:
        timeout = min(timeout, deadline - started)
        if timeout <= 0:
            return SuiteResult(status="ERROR", reason="Run deadline exceeded")
    try:
        process = run_process(
            command,
            cwd=harness,
            env=env,
            log=log,
            timeout=timeout,
            output_limit=output_limit,
            secrets=secrets,
            cancel=cancel,
        )
        if process.timed_out or process.output_limited or process.cancelled:
            result = SuiteResult(
                status="ERROR",
                reason=(
                    "Test process timed out"
                    if process.timed_out
                    else "Suite cancelled"
                    if process.cancelled
                    else "Test output limit exceeded"
                ),
            )
        else:
            result = parse_junit(report, process.exit_code, output_limit)
    except ArtifactQuotaExceeded:
        raise
    except (OSError, RuntimeError) as exc:
        log.write_text(type(exc).__name__, encoding="utf-8")
        result = SuiteResult(status="ERROR", reason=f"Test process error: {type(exc).__name__}")
    result.duration_ms = int((time.monotonic() - started) * 1000)
    result.log_file = str(log)
    return result
