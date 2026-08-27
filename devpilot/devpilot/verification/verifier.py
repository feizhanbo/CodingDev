"""Verification logic."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from devpilot.domain.decision import ToolAction
from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.context import ToolContext
from devpilot.tools.registry import ToolRegistry

_FORBIDDEN_FILES = {".env", ".git/config", "id_rsa", "id_ed25519"}
_MAX_MODIFIED_FILES = 10


class VerificationResult(BaseModel):
    """Result of running all verification checks."""

    success: bool
    checks: list[dict[str, Any]]
    failure_reason: str | None = None


class TaskVerifier:
    """Deterministic final verifier that runs before a task is marked complete."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    async def verify(
        self,
        task: DevelopmentTask,
        workspace_path: str,
        state: DevPilotState,
        registry: ToolRegistry,
    ) -> VerificationResult:
        """Run all verification checks and return the aggregated result."""
        checks: list[dict[str, Any]] = []

        test_check = await self._check_visible_tests(
            workspace_path, state.run_id, registry
        )
        checks.append(test_check)

        diff_check = await self._check_diff_non_empty(
            workspace_path, state.run_id, registry
        )
        checks.append(diff_check)

        forbidden_check = self._check_forbidden_files(state)
        checks.append(forbidden_check)

        count_check = self._check_modified_file_count(state)
        checks.append(count_check)

        all_passed = all(c["passed"] for c in checks)
        failed_checks = [c for c in checks if not c["passed"]]
        failure_reason = (
            "; ".join(c["message"] for c in failed_checks)
            if failed_checks
            else None
        )

        return VerificationResult(
            success=all_passed,
            checks=checks,
            failure_reason=failure_reason,
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

    def _check_forbidden_files(
        self, state: DevPilotState
    ) -> dict[str, Any]:
        """Check that no forbidden files were modified."""
        modified_forbidden = [
            f
            for f in state.modified_files
            if any(x in f for x in _FORBIDDEN_FILES)
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

    def _check_modified_file_count(
        self, state: DevPilotState
    ) -> dict[str, Any]:
        """Check that modified file count is within the limit."""
        count = len(state.modified_files)
        if count <= _MAX_MODIFIED_FILES:
            return {
                "name": "modified_file_count",
                "passed": True,
                "message": f"{count} files modified (limit: {_MAX_MODIFIED_FILES})",
            }
        return {
            "name": "modified_file_count",
            "passed": False,
            "message": f"{count} files modified exceeds limit of {_MAX_MODIFIED_FILES}",
        }
