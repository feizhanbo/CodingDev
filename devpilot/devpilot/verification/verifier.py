"""Verification logic."""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from devpilot.domain.decision import ToolAction
from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.processes import run_cancellable
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.context import ToolContext
from devpilot.tools.registry import ToolRegistry
from devpilot.verification.evidence import is_test, materialize_candidate, read_manifest

_FORBIDDEN_FILES = {".env", ".git/config", "id_rsa", "id_ed25519"}
_MAX_MODIFIED_FILES = 10


class VerificationResult(BaseModel):
    """Result of running all verification checks."""

    success: bool
    checks: list[dict[str, Any]]
    failure_reason: str | None = None
    coverage: list[dict] = []
    evidence_ref: str | None = None


class TaskVerifier:
    """Deterministic final verifier that runs before a task is marked complete."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self._snapshots: dict[str, Path] = {}
        self.last_results: dict[str, dict] = {}
        self.deadline: float | None = None

    def _timeout(self) -> float:
        remaining = self.config.test_timeout_seconds
        if self.deadline is not None:
            remaining = min(remaining, self.deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Run deadline exceeded before verification")
        return remaining

    def bind_snapshot(self, run_id: str, trusted: Path) -> None:
        self._snapshots[run_id] = trusted

    async def verify(
        self,
        task: DevelopmentTask,
        workspace_path: str,
        state: DevPilotState,
        registry: ToolRegistry,
    ) -> VerificationResult:
        """Run all verification checks and return the aggregated result."""
        from devpilot.evals.benchmark import run_independent_suite

        checks: list[dict[str, Any]] = []
        trusted = self._snapshots.get(state.run_id)
        if trusted is None:
            return VerificationResult(
                success=False,
                checks=[
                    {
                        "name": "trusted_baseline",
                        "passed": False,
                        "message": "No frozen baseline was registered before the agent run",
                    }
                ],
                failure_reason="Missing trusted baseline",
            )
        try:
            candidate, diff, changed = materialize_candidate(
                Path(workspace_path),
                trusted,
                trusted.parent,
            )
        except (OSError, ValueError, PermissionError, RuntimeError) as exc:
            return VerificationResult(
                success=False,
                checks=[
                    {
                        "name": (
                            "forbidden_files"
                            if "forbidden" in str(exc).lower()
                            else "test_integrity"
                        ),
                        "passed": False,
                        "message": str(exc),
                    }
                ],
                failure_reason=str(exc),
            )
        # Actual files, including untracked additions and deletions, are authoritative.
        state.modified_files = changed
        checks.append(
            {
                "name": "test_integrity",
                "passed": True,
                "message": "Frozen tests and configuration are intact",
            }
        )
        checks.append(
            {
                "name": "diff_non_empty",
                "passed": bool(diff.strip()),
                "message": "Git diff is non-empty" if diff.strip() else "Git diff is empty",
            }
        )
        checks.append(self._check_forbidden_files(state))
        checks.append(self._check_modified_file_count(state))
        manifest = read_manifest(trusted)
        baseline_tests = candidate.parent / "baseline-tests"
        new_tests = candidate.parent / "added-tests"
        baseline_tests.mkdir()
        new_tests.mkdir()
        for relative in manifest["protected"]:
            source = trusted / "baseline" / relative
            if source.suffix != ".py":
                continue
            target = baseline_tests / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if source.name in {"conftest.py", "__init__.py"}:
                target = new_tests / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        additions = [p for p in changed if p not in manifest["files"] and is_test(p)]
        for relative in additions:
            target = new_tests / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate / relative, target)
        test_tool = registry.get("test.run")
        python = getattr(test_tool, "python_executable", sys.executable)
        visible = await run_cancellable(
            run_independent_suite,
            candidate,
            baseline_tests,
            candidate.parent / "visible",
            python,
            timeout=self._timeout(),
            trusted_fixtures=False,
            deadline=self.deadline,
            output_limit=self.config.max_test_output_bytes,
            secrets=getattr(test_tool, "secrets", ()),
        )
        checks.append(
            {
                "name": "visible_tests",
                "passed": visible.status == "PASS" and not visible.skipped,
                "message": visible.reason or f"{visible.passed} passed, {visible.failed} failed",
                "result": visible.model_dump(),
            }
        )
        added = None
        if additions:
            added = await run_cancellable(
                run_independent_suite,
                candidate,
                new_tests,
                candidate.parent / "added",
                python,
                timeout=self._timeout(),
                trusted_fixtures=False,
                deadline=self.deadline,
                output_limit=self.config.max_test_output_bytes,
                secrets=getattr(test_tool, "secrets", ()),
            )
            checks.append(
                {
                    "name": "added_tests",
                    "passed": added.status == "PASS" and not added.skipped,
                    "message": added.reason or f"{added.passed} added tests passed",
                    "result": added.model_dump(),
                }
            )
        criteria = " ".join(task.acceptance_criteria).lower()
        if any(term in criteria for term in ("add tests", "新增测试", "新增回归测试")):
            checks.append(
                {
                    "name": "required_new_tests",
                    "passed": bool(additions),
                    "message": "New tests supplied" if additions else "Issue requires new tests",
                }
            )
        (trusted.parent / "final.diff").write_text(diff, encoding="utf-8", newline="")
        self.last_results[state.run_id] = {
            "visible": visible.model_dump(),
            "added": added.model_dump() if added else None,
            "candidate": str(candidate),
            "modified_files": changed,
        }
        failed = [c["message"] for c in checks if not c["passed"]]
        return VerificationResult(
            success=not failed, checks=checks, failure_reason="; ".join(failed) if failed else None,
            coverage=coverage_for(task, checks), evidence_ref=str(candidate.parent),
        )

    async def _check_visible_tests(
        self,
        workspace_path: str,
        run_id: str,
        registry: ToolRegistry,
    ) -> dict[str, Any]:
        """Run pytest via the test.run tool and check results."""
        action = ToolAction(tool="test.run", arguments={})
        ctx = ToolContext(workspace_root=workspace_path, run_id=run_id)
        result = await registry.execute(action, ctx)

        if result.success:
            passed = result.data.get("passed") if result.data else None
            failed = result.data.get("failed") if result.data else None
            return {
                "name": "visible_tests",
                "passed": True,
                "message": f"Tests passed: {passed or 0} passed, {failed or 0} failed",
            }
        exit_code = result.data.get("exit_code") if result.data else None
        return {
            "name": "visible_tests",
            "passed": False,
            "message": f"Tests failed (exit code: {exit_code})",
        }

    async def _check_diff_non_empty(
        self,
        workspace_path: str,
        run_id: str,
        registry: ToolRegistry,
    ) -> dict[str, Any]:
        """Check that git diff is not empty."""
        action = ToolAction(tool="git.diff", arguments={})
        ctx = ToolContext(workspace_root=workspace_path, run_id=run_id)
        result = await registry.execute(action, ctx)

        if not result.success:
            return {
                "name": "diff_non_empty",
                "passed": False,
                "message": result.error or "git diff failed",
            }
        diff = result.data.get("diff", "") if result.data else ""
        if diff.strip():
            return {
                "name": "diff_non_empty",
                "passed": True,
                "message": "Git diff is non-empty",
            }
        return {
            "name": "diff_non_empty",
            "passed": False,
            "message": "Git diff is empty - no changes made",
        }

    def _check_forbidden_files(self, state: DevPilotState) -> dict[str, Any]:
        """Check that no forbidden files were modified."""
        modified_forbidden = [
            f for f in state.modified_files if any(x in f for x in _FORBIDDEN_FILES)
        ]
        if not modified_forbidden:
            return {
                "name": "forbidden_files",
                "passed": True,
                "message": "No forbidden files modified",
            }
        return {
            "name": "forbidden_files",
            "passed": False,
            "message": f"Forbidden files modified: {modified_forbidden}",
        }

    def _check_modified_file_count(self, state: DevPilotState) -> dict[str, Any]:
        """Check that modified file count is within the limit."""
        count = len(state.modified_files)
        if count <= self.config.max_modified_files:
            return {
                "name": "modified_file_count",
                "passed": True,
                "message": f"{count} files modified (limit: {self.config.max_modified_files})",
            }
        return {
            "name": "modified_file_count",
            "passed": False,
            "message": f"{count} files modified exceeds limit of {self.config.max_modified_files}",
        }


def coverage_for(task: DevelopmentTask, checks: list[dict]) -> list[dict]:
    by_name = {c["name"]: c for c in checks}
    coverage = []
    for index, criterion in enumerate(task.acceptance_criteria):
        mapped = (
            ["required_new_tests"]
            if any(term in criterion.lower() for term in ("add tests", "新增测试", "新增回归测试"))
            else []
        )
        available = [by_name[name] for name in mapped if name in by_name]
        status = (
            "uncovered" if not available
            else "verified" if all(c["passed"] for c in available) else "failed"
        )
        coverage.append({
            "index": index, "criterion": criterion, "checks": mapped,
            "status": status,
            "evidence_refs": [c.get("result", {}).get("report_file") for c in available
                              if c.get("result", {}).get("report_file")],
            "reason": "No deterministic check bound to this condition" if not available else None,
        })
    return coverage
