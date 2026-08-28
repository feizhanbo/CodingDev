"""Evaluation runner for DevPilot issues."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from devpilot.cli import initialize_components, load_issue
from devpilot.domain.result import AgentRunResult
from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.runner import CustomAgentRunner
from devpilot.workspace.sandbox import SandboxWorkspace

_PASSED_RE = re.compile(r"(\d+) passed")
_FAILED_RE = re.compile(r"(\d+) failed")


class EvalResult(BaseModel):
    """Result of evaluating a single issue."""

    issue_id: str
    run_id: str
    task_success: bool
    visible_test_pass_rate: float
    hidden_test_pass_rate: float | None = None
    regression_rate: float = 0.0
    avg_steps: int = 0
    avg_test_retries: int = 0
    tool_failure_rate: float = 0.0
    change_scope: dict = {}
    token_cost: int | None = None
    runtime_duration_ms: int = 0
    agent_status: str
    error: str | None = None


class EvalRunner:
    """Runs evaluations on DevPilot issues with hidden tests and metrics."""

    def __init__(
        self,
        base_repo_path: str,
        issues_dir: str = "evals/issues",
        hidden_tests_dir: str = "evals/hidden_tests",
        config: RuntimeConfig | None = None,
    ) -> None:
        self.base_repo = Path(base_repo_path).resolve()
        self.issues_dir = Path(issues_dir)
        self.hidden_tests_dir = Path(hidden_tests_dir)
        self.config = config or RuntimeConfig()

    async def run_eval(
        self,
        issue_id: str,
        fake: bool = False,
        on_event: Callable[[str, dict], None] | None = None,
    ) -> EvalResult:
        """Run evaluation for a single issue."""
        # 1. Load issue
        issue_file = self.issues_dir / f"{issue_id}.yaml"
        task = load_issue(str(issue_file))

        # 2. Initialize components
        runner = self._init_components(fake=fake, on_event=on_event)

        # 3. Run DevPilot
        run_result = await runner.run(task)

        # 4. Run visible tests check (extract from run result)
        visible_pass_rate = self._check_visible_tests(run_result)

        # 5. Save final diff
        final_diff = self._save_final_diff(
            run_result.run_id, runner.sandbox
        )

        # 6. Run hidden tests (after agent completes)
        hidden_result = self._run_hidden_tests(
            issue_id, run_result.run_id, runner.sandbox
        )

        # 7. Load state for metrics
        state = self._load_state(run_result.run_id, runner.sandbox)

        # 8. Collect metrics
        metrics = self._collect_metrics(run_result, state)

        # 9. Calculate tool failure rate
        tool_calls = metrics.get("tool_calls", 0)
        tool_failures = metrics.get("tool_failures", 0)
        tool_failure_rate = (
            tool_failures / tool_calls if tool_calls > 0 else 0.0
        )

        # 10. Calculate change scope
        change_scope = self._calculate_change_scope(
            run_result, final_diff
        )

        # 11. Build EvalResult
        eval_result = EvalResult(
            issue_id=issue_id,
            run_id=run_result.run_id,
            task_success=(
                run_result.status == "completed"
                and hidden_result.get("passed", True)
            ),
            visible_test_pass_rate=visible_pass_rate,
            hidden_test_pass_rate=hidden_result.get("pass_rate"),
            avg_steps=run_result.total_steps,
            avg_test_retries=metrics.get("test_retries", 0),
            tool_failure_rate=round(tool_failure_rate, 4),
            change_scope=change_scope,
            runtime_duration_ms=run_result.duration_ms or 0,
            agent_status=run_result.status,
            error=run_result.error,
        )

        # 12. Save EvalResult
        runner.sandbox.save_artifact(
            run_result.run_id,
            "eval_result.json",
            eval_result.model_dump_json(indent=2),
        )

        return eval_result

    async def run_all(
        self,
        fake: bool = False,
        on_event: Callable[[str, dict], None] | None = None,
    ) -> list[EvalResult]:
        """Run evaluation for all issues."""
        results: list[EvalResult] = []
        issue_files = sorted(self.issues_dir.glob("DEV-*.yaml"))
        for issue_file in issue_files:
            issue_id = issue_file.stem
            result = await self.run_eval(
                issue_id, fake=fake, on_event=on_event
            )
            results.append(result)
        return results

    def _init_components(
        self,
        fake: bool = False,
        on_event: Callable[[str, dict], None] | None = None,
    ) -> CustomAgentRunner:
        """Initialize runner with all components."""
        return initialize_components(
            self.config,
            fake=fake,
            base_repo=str(self.base_repo),
            on_event=on_event,
        )

    def _check_visible_tests(self, run_result: AgentRunResult) -> float:
        """Check visible test pass rate from run result.

        Looks at test.run observations and verifier outcomes.
        Returns 1.0 if all visible tests passed, 0.0 if failed.
        """
        # If run completed, verifier passed -> visible tests passed
        if run_result.status == "completed":
            return 1.0

        # If run failed, check test.run observations for pass rate
        test_obs = [
            o for o in run_result.observations
            if o.source == "tool" and o.name == "test.run"
        ]
        if not test_obs:
            return 0.0

        # Use the last test run for pass rate
        last_test = test_obs[-1]
        if last_test.data:
            passed = last_test.data.get("passed")
            failed = last_test.data.get("failed")
            if passed is not None and failed is not None:
                total = passed + failed
                if total > 0:
                    return passed / total
        return 0.0 if not last_test.success else 1.0

    def _run_hidden_tests(
        self,
        issue_id: str,
        run_id: str,
        sandbox: SandboxWorkspace,
    ) -> dict:
        """Run hidden tests independently after agent completes.

        Hidden tests are copied to the workspace after the agent run,
        then pytest is executed on them.
        """
        hidden_test_dir = self.hidden_tests_dir / issue_id
        if not hidden_test_dir.exists():
            return {"passed": True, "pass_rate": None, "details": "No hidden tests"}

        workspace_repo = Path(sandbox.get_repo_path(run_id))
        hidden_dest = workspace_repo / "hidden_tests"
        hidden_dest.mkdir(parents=True, exist_ok=True)

        # Copy hidden test files to workspace
        copied_files: list[Path] = []
        for test_file in hidden_test_dir.rglob("*.py"):
            rel = test_file.relative_to(hidden_test_dir)
            dest = hidden_dest / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(test_file, dest)
            copied_files.append(dest)

        if not copied_files:
            return {"passed": True, "pass_rate": None, "details": "No hidden test files"}

        # Run pytest on hidden tests
        cmd = [
            sys.executable, "-m", "pytest",
            str(hidden_dest), "-v", "--tb=short",
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workspace_repo),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return {
                "passed": False,
                "pass_rate": 0.0,
                "details": f"Hidden test execution error: {exc}",
            }

        output = proc.stdout + proc.stderr
        passed = _first_int(_PASSED_RE, output)
        failed = _first_int(_FAILED_RE, output)

        if passed is None and failed is None:
            # No test results parsed
            all_pass = proc.returncode == 0
            return {
                "passed": all_pass,
                "pass_rate": 1.0 if all_pass else 0.0,
                "details": "No test counts parsed",
            }

        total = (passed or 0) + (failed or 0)
        pass_rate = (passed or 0) / total if total > 0 else 0.0
        return {
            "passed": proc.returncode == 0,
            "pass_rate": round(pass_rate, 4),
            "details": f"{passed or 0} passed, {failed or 0} failed",
        }

    def _load_state(
        self, run_id: str, sandbox: SandboxWorkspace
    ) -> DevPilotState:
        """Load saved state from runs directory."""
        runs_dir = Path(sandbox.get_runs_dir(run_id))
        state_file = runs_dir / "state.json"
        if state_file.is_file():
            content = state_file.read_text(encoding="utf-8")
            return DevPilotState.model_validate_json(content)
        # Return a minimal state if file not found
        return DevPilotState(
            run_id=run_id,
            task=DevelopmentTask(
                id="unknown",
                title="unknown",
                description="",
                acceptance_criteria=[],
            ),
            phase="failed",
        )

    def _collect_metrics(
        self, run_result: AgentRunResult, state: DevPilotState
    ) -> dict:
        """Collect metrics from run result and state."""
        tool_calls = sum(
            1 for o in run_result.observations if o.source == "tool"
        )
        tool_failures = sum(
            1 for o in run_result.observations
            if o.source == "tool" and not o.success
        )
        return {
            "total_steps": run_result.total_steps,
            "tool_calls": tool_calls,
            "tool_failures": tool_failures,
            "test_retries": state.retry_count,
            "modified_files": len(run_result.modified_files),
            "duration_ms": run_result.duration_ms or 0,
        }

    def _save_final_diff(
        self, run_id: str, sandbox: SandboxWorkspace
    ) -> str:
        """Get git diff from workspace and save as final.diff artifact."""
        workspace_repo = Path(sandbox.get_repo_path(run_id))
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD", "--no-color"],
                cwd=str(workspace_repo),
                capture_output=True,
                text=True,
            )
            diff = result.stdout
        except (OSError, subprocess.SubprocessError):
            diff = ""
        sandbox.save_artifact(run_id, "final.diff", diff)
        return diff

    def _calculate_change_scope(
        self, run_result: AgentRunResult, diff: str
    ) -> dict:
        """Calculate the scope of changes (files and lines)."""
        files = len(run_result.modified_files)
        lines = 0
        if diff:
            for line in diff.splitlines():
                if (
                    (line.startswith("+") and not line.startswith("+++"))
                    or (
                        line.startswith("-")
                        and not line.startswith("---")
                    )
                ):
                    lines += 1
        return {"files": files, "lines": lines}

    def generate_summary(self, results: list[EvalResult]) -> str:
        """Generate a summary table of all eval results."""
        if not results:
            return "No evaluation results to display."

        lines: list[str] = []
        header = (
            f"{'Issue':<10} {'Status':<12} {'Success':<8} "
            f"{'Visible%':<10} {'Hidden%':<10} {'Steps':<6} "
            f"{'Retries':<8} {'Duration':<10}"
        )
        lines.append(header)
        lines.append("-" * len(header))

        for r in results:
            visible_pct = f"{r.visible_test_pass_rate * 100:.0f}%"
            hidden_pct = (
                f"{r.hidden_test_pass_rate * 100:.0f}%"
                if r.hidden_test_pass_rate is not None
                else "N/A"
            )
            duration = f"{r.runtime_duration_ms}ms"
            success = "YES" if r.task_success else "NO"
            lines.append(
                f"{r.issue_id:<10} {r.agent_status:<12} {success:<8} "
                f"{visible_pct:<10} {hidden_pct:<10} "
                f"{r.avg_steps:<6} {r.avg_test_retries:<8} "
                f"{duration:<10}"
            )

        # Summary line
        total = len(results)
        successes = sum(1 for r in results if r.task_success)
        lines.append("-" * len(header))
        lines.append(
            f"Total: {total}, Success: {successes}, "
            f"Fail: {total - successes}"
        )
        return "\n".join(lines)

    def generate_comparison_table(
        self, results: list[EvalResult]
    ) -> str:
        """Generate a markdown comparison table."""
        if not results:
            return "No results to compare."

        lines: list[str] = []
        lines.append(
            "| Issue | Status | Success | Visible% | Hidden% | "
            "Steps | Retries | Duration |"
        )
        lines.append(
            "|-------|--------|---------|----------|---------|"
            "-------|---------|----------|"
        )
        for r in results:
            visible_pct = f"{r.visible_test_pass_rate * 100:.0f}%"
            hidden_pct = (
                f"{r.hidden_test_pass_rate * 100:.0f}%"
                if r.hidden_test_pass_rate is not None
                else "N/A"
            )
            duration = f"{r.runtime_duration_ms}ms"
            success = "YES" if r.task_success else "NO"
            lines.append(
                f"| {r.issue_id} | {r.agent_status} | {success} | "
                f"{visible_pct} | {hidden_pct} | "
                f"{r.avg_steps} | {r.avg_test_retries} | {duration} |"
            )
        return "\n".join(lines)


def _first_int(pattern: re.Pattern[str], text: str) -> int | None:
    """Return the first integer matched by *pattern* in *text*."""
    m = pattern.search(text)
    return int(m.group(1)) if m else None
