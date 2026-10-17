"""Versioned task starting points and independent benchmark self-validation.

Only the evaluator imports this module. Reference patches and hidden tests must
never be placed in the Agent workspace, prompts, observations or tool results.
"""

from __future__ import annotations

import ast
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, Field

from devpilot.processes import run_process
from devpilot.security import process_environment
from devpilot.workspace.sandbox import SandboxWorkspace, _git_init


class SuiteResult(BaseModel):
    status: str
    collected: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    assertion_failures: int = 0
    duration_ms: int = 0
    node_outcomes: dict[str, str] = Field(default_factory=dict)
    reason: str | None = None
    report_file: str | None = None
    log_file: str | None = None


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resource_root() -> Path:
    return Path(str(files("devpilot.evals")))


def packaged_baseline() -> Path:
    return resource_root() / "benchmark" / "baseline"


def load_manifest() -> dict:
    return json.loads((resource_root() / "benchmark/manifest.json").read_text(encoding="utf-8"))


def _safe_child(root: Path, relative: str) -> Path:
    candidate = root / relative
    if Path(relative).is_absolute() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Invalid dataset path: {relative}")
    return candidate


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout


def verify_resources(issue_id: str, manifest: dict | None = None) -> None:
    manifest = manifest or load_manifest()
    if issue_id not in manifest["issues"]:
        raise ValueError(f"Unknown benchmark issue: {issue_id}")
    for relative, expected in manifest["issues"][issue_id]["resources"].items():
        source = _safe_child(resource_root(), relative)
        if digest(source.read_text(encoding="utf-8")) != expected:
            raise ValueError(f"Dataset resource changed without version update: {relative}")


def apply_dataset_patch(repo: Path, issue_id: str, kind: str) -> None:
    manifest = load_manifest()
    if issue_id not in manifest["issues"] or kind not in {"start", "reference"}:
        raise ValueError("Unknown dataset issue or patch kind")
    verify_resources(issue_id, manifest)
    patch = resource_root() / "benchmark" / issue_id / f"{kind}.patch"
    content = patch.read_text(encoding="utf-8")
    if digest(content) != manifest["issues"][issue_id][f"{kind}_patch_sha256"]:
        raise ValueError(f"Corrupt {issue_id} {kind} patch")
    if content.strip():
        _run_git(repo, "apply", "--check", str(patch))
        _run_git(repo, "apply", str(patch))


def prepare_task(base_repo: Path, destination: Path, issue_id: str) -> dict:
    """Copy exactly the pinned, hash-checked input; never copy host extras/secrets."""
    manifest = load_manifest()
    if issue_id not in manifest["issues"]:
        raise ValueError(f"Unknown benchmark issue: {issue_id}")
    verify_resources(issue_id, manifest)
    if destination.exists():
        raise FileExistsError(destination)
    contents = {}
    for relative, expected in manifest["baseline_files"].items():
        source = _safe_child(base_repo, relative)
        if source.is_symlink() or (hasattr(source, "is_junction") and source.is_junction()):
            raise ValueError(f"Linked baseline file: {relative}")
        value = source.read_text(encoding="utf-8")
        if digest(value) != expected:
            raise ValueError(f"Baseline differs from {manifest['baseline_commit']}: {relative}")
        contents[relative] = value
    for relative, value in contents.items():
        path = _safe_child(destination, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8", newline="")
    _git_init(destination)
    apply_dataset_patch(destination, issue_id, "start")
    _run_git(destination, "add", "-A")
    _run_git(destination, "commit", "--allow-empty", "-m", f"{issue_id} fixed starting point")
    return {
        "dataset_version": manifest["dataset_version"],
        "baseline_commit": manifest["baseline_commit"],
        "start_patch_sha256": manifest["issues"][issue_id]["start_patch_sha256"],
        "starting_tree": _run_git(destination, "rev-parse", "HEAD^{tree}").strip(),
    }


def parse_junit(path: Path, exit_code: int) -> SuiteResult:
    """A zero exit status without meaningful, valid test evidence is not PASS."""
    if not path.is_file():
        return SuiteResult(status="ERROR", reason="Missing structured test report")
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return SuiteResult(status="ERROR", reason=f"Invalid structured test report: {exc}")
    result = SuiteResult(status="ERROR", report_file=str(path))
    for case in root.iter("testcase"):
        result.collected += 1
        key = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("error") is not None:
            result.errors += 1
            outcome = "ERROR"
        elif case.find("failure") is not None:
            result.failed += 1
            failure = case.find("failure")
            details = (failure.get("message", "") or "") + (failure.text or "")
            if "AssertionError" in details or "assert " in details:
                result.assertion_failures += 1
            outcome = "FAIL"
        elif case.find("skipped") is not None:
            result.skipped += 1
            outcome = "SKIP"
        else:
            result.passed += 1
            outcome = "PASS"
        # Duplicate node identities make cross-run regression statistics ambiguous.
        if key in result.node_outcomes:
            result.reason = "Duplicate test identity in report"
            return result
        result.node_outcomes[key] = outcome
    if result.errors or exit_code not in (0, 1):
        result.reason = f"Test execution/collection error (exit {exit_code})"
    elif result.collected == 0 or result.passed + result.failed == 0:
        result.reason = "No executed tests (empty or all skipped)"
    elif result.failed:
        result.status = "FAIL"
    elif exit_code == 0:
        result.status = "PASS"
    else:
        result.reason = "Process exit disagrees with structured report"
    return result


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
    trusted_fixtures: bool = True,
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
        tests_source, suite, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache")
    )
    if trusted_fixtures:
        shutil.copyfile(resource_root() / "shared/conftest.py", suite / "conftest.py")
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
            result = parse_junit(report, process.exit_code)
    except (OSError, RuntimeError) as exc:
        log.write_text(type(exc).__name__, encoding="utf-8")
        result = SuiteResult(status="ERROR", reason=f"Test process error: {type(exc).__name__}")
    result.duration_ms = int((time.monotonic() - started) * 1000)
    result.log_file = str(log)
    return result


def validate_benchmark(
    base_repo: Path, output: Path, python: str, *, performance: bool = False
) -> dict:
    """Prove each defect is detectable and reference fix passes hidden+visible suites."""
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": 1,
        "dataset_version": load_manifest()["dataset_version"],
        "platform": platform.platform(),
        "python": python,
        "issues": {},
        "passed": None,
        "status": "running",
        "planned_count": len(load_manifest()["issues"]),
    }
    for issue_id in load_manifest()["issues"]:
        folder = output / issue_id
        folder.mkdir(exist_ok=True)
        candidate = folder / "repo"
        entry = {}
        try:
            entry["starting_point"] = prepare_task(base_repo, candidate, issue_id)
            hidden_source = resource_root() / "hidden_tests" / issue_id
            negative = run_independent_suite(candidate, hidden_source, folder / "negative", python)
            entry["negative"] = negative.model_dump()
            apply_dataset_patch(candidate, issue_id, "reference")
            positive = run_independent_suite(candidate, hidden_source, folder / "positive", python)
            entry["positive"] = positive.model_dump()
            visible = run_independent_suite(
                candidate, candidate / "tests", folder / "visible", python
            )
            entry["visible"] = visible.model_dump()
            entry["passed"] = (
                negative.status == "FAIL"
                and negative.assertion_failures > 0
                and negative.errors == 0
                and positive.status == "PASS"
                and positive.skipped == 0
                and visible.status == "PASS"
                and visible.skipped == 0
            )
            if performance and issue_id == "DEV-005":
                perf = run_independent_suite(
                    candidate, hidden_source, folder / "performance", python, performance=True
                )
                entry["performance"] = perf.model_dump()
                entry["passed"] = entry["passed"] and perf.status == "PASS"
        except Exception as exc:
            entry.update(passed=False, error=str(exc))
        summary["issues"][issue_id] = entry
        summary["completed_count"] = len(summary["issues"])
        complete = summary["completed_count"] == summary["planned_count"]
        summary["status"] = "completed" if complete else "running"
        summary["passed"] = (
            all(e["passed"] for e in summary["issues"].values()) if complete else None
        )
        (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"{issue_id}: {'PASS' if entry['passed'] else 'FAIL'}", flush=True)
    return summary


class BenchmarkWorkspace(SandboxWorkspace):
    """Create the task-specific starting point directly as the Agent workspace."""

    def __init__(self, issue_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.issue_id = issue_id

    def create(self, run_id: str) -> str:
        repo = Path(self.get_repo_path(run_id))
        self.check_capacity(
            sum((self.base_repo / p).stat().st_size for p in load_manifest()["baseline_files"])
        )
        metadata = prepare_task(self.base_repo, repo, self.issue_id)
        metadata.update(run_id=run_id, workspace_path=str(repo), base_repo=str(self.base_repo))
        self.save_artifact(run_id, "workspace-metadata.json", json.dumps(metadata, indent=2))
        return str(repo)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--test-python", default=sys.executable)
    parser.add_argument("--performance", action="store_true")
    args = parser.parse_args()
    result = validate_benchmark(
        args.base_repo.resolve(),
        args.output.resolve(),
        args.test_python,
        performance=args.performance,
    )
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
