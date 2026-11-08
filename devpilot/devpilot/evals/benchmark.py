"""Versioned task starting points and independent benchmark self-validation.

Only the evaluator imports this module. Reference patches and hidden tests must
never be placed in the Agent workspace, prompts, observations or tool results.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from importlib.resources import files
from pathlib import Path

from devpilot.processes import capture_process
from devpilot.workspace.sandbox import SandboxWorkspace, _git_init


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
    result = capture_process(
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


# Compatibility exports for existing reports and integrations.
from devpilot.testing.junit import SuiteResult, parse_junit  # noqa: E402, F401
from devpilot.testing.suite import has_behavior_assertions  # noqa: E402, F401
from devpilot.testing.suite import run_independent_suite as _run_suite  # noqa: E402


def run_independent_suite(*args, trusted_fixtures=True, **kwargs):
    return _run_suite(
        *args,
        trusted_fixtures=trusted_fixtures,
        fixtures_path=resource_root() / "shared/conftest.py",
        **kwargs,
    )


if __name__ == "__main__":
    main()
