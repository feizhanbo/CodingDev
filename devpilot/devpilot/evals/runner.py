"""Evaluation runner for DevPilot issues."""

from __future__ import annotations

import asyncio
import re
import subprocess
import uuid
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from devpilot.cli import initialize_components, load_issue
from devpilot.domain.result import AgentRunResult
from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.runner import CustomAgentRunner
from devpilot.settings import Settings
from devpilot.workspace.sandbox import SandboxWorkspace

_PASSED_RE = re.compile(r"(\d+) passed")
_FAILED_RE = re.compile(r"(\d+) failed")


class EvalResult(BaseModel):
    """Result of evaluating a single issue."""

    schema_version: int = 2
    evaluation_mode: Literal["smoke", "capability"] = "capability"
    evaluation_status: Literal["PASS", "FAIL", "NOT_EVALUATED", "ERROR"] = "NOT_EVALUATED"
    evaluation_reason: str | None = None
    verification: dict = Field(default_factory=dict)
    issue_id: str
    run_id: str
    task_success: bool | None
    visible_test_pass_rate: float | None
    hidden_test_pass_rate: float | None = None
    regression_rate: float | None = None
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
        issues_dir: str | None = None,
        hidden_tests_dir: str | None = None,
        config: RuntimeConfig | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.base_repo = Path(base_repo_path).resolve()
        self.issues_dir = (
            Path(issues_dir) if issues_dir else Path(str(files("devpilot.evals") / "issues"))
        )
        self.hidden_tests_dir = (
            Path(hidden_tests_dir)
            if hidden_tests_dir
            else Path(str(files("devpilot.evals") / "hidden_tests"))
        )
        self.settings = settings or Settings()
        self.config = config or self.settings.runtime_config()

    async def run_eval(
        self,
        issue_id: str,
        fake: bool = False,
        on_event: Callable[[str, dict], None] | None = None,
    ) -> EvalResult:
        """Run evaluation for a single issue."""
        from devpilot.evals.benchmark import BenchmarkWorkspace, resource_root

        mode = "smoke" if fake else "capability"
        fallback_id = f"eval_error_{uuid.uuid4().hex[:12]}"
        try:
            task = load_issue(str(self.issues_dir / f"{issue_id}.yaml"))
            runner = self._init_components(fake=fake, on_event=on_event)
            builtin = self.issues_dir.resolve() == (resource_root() / "issues").resolve()
            if builtin and not fake:
                runner.sandbox = BenchmarkWorkspace(
                    issue_id=issue_id,
                    base_repo_path=str(self.base_repo),
                    workspace_root=str(runner.sandbox.workspace_root),
                    runs_root=str(runner.sandbox.runs_root),
                )
            run_result = await runner.run(task)
            evidence = runner.verifier.last_results.get(run_result.run_id, {})
            visible = evidence.get("visible", {})
            hidden = (
                {"status": "NOT_EVALUATED", "details": "Smoke does not run hidden acceptance tests"}
                if fake
                else await asyncio.to_thread(
                    self._run_hidden_tests, issue_id, run_result.run_id, runner.sandbox
                )
            )
            if fake:
                status = "PASS" if run_result.status == "completed" else "FAIL"
                reason = "Runtime smoke only; excluded from capability success rate"
            elif hidden.get("status") in {"NOT_EVALUATED", "ERROR"}:
                status, reason = hidden["status"], hidden.get("details")
            elif run_result.status != "completed":
                status, reason = "FAIL", run_result.error
            elif visible.get("status") != "PASS":
                status, reason = "ERROR", "Missing trusted visible-test evidence"
            else:
                status = "PASS" if hidden.get("passed") else "FAIL"
                reason = hidden.get("details")
            final_diff = self._save_final_diff(run_result.run_id, runner.sandbox)
            state = self._load_state(run_result.run_id, runner.sandbox)
            metrics = self._collect_metrics(run_result, state)
            total = visible.get("passed", 0) + visible.get("failed", 0)
            evaluation = EvalResult(
                issue_id=issue_id,
                run_id=run_result.run_id,
                evaluation_mode=mode,
                evaluation_status=status,
                evaluation_reason=reason,
                task_success=(
                    status == "PASS" if not fake and status in {"PASS", "FAIL"} else None
                ),
                visible_test_pass_rate=visible.get("passed", 0) / total if total else None,
                hidden_test_pass_rate=hidden.get("pass_rate"),
                avg_steps=run_result.total_steps,
                avg_test_retries=metrics.get("test_retries", 0),
                tool_failure_rate=round(metrics["tool_failures"] / metrics["tool_calls"], 4)
                if metrics["tool_calls"]
                else 0.0,
                change_scope=self._calculate_change_scope(run_result, final_diff),
                runtime_duration_ms=run_result.duration_ms or 0,
                agent_status=run_result.status,
                error=run_result.error,
                verification={"visible": visible, "hidden": hidden, "added": evidence.get("added")},
            )
            runner.sandbox.save_artifact(
                run_result.run_id, "eval_result.json", evaluation.model_dump_json(indent=2)
            )
            return evaluation
        except Exception as exc:
            evaluation = EvalResult(
                issue_id=issue_id,
                run_id=fallback_id,
                evaluation_mode=mode,
                evaluation_status="ERROR",
                evaluation_reason=str(exc),
                error=str(exc),
                task_success=None,
                visible_test_pass_rate=None,
                agent_status="failed",
            )
            directory = Path(self.settings.runs_root) / fallback_id
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "eval_result.json").write_text(
                evaluation.model_dump_json(indent=2), encoding="utf-8"
            )
            return evaluation

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
            result = await self.run_eval(issue_id, fake=fake, on_event=on_event)
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
            base_repo=None if fake else str(self.base_repo),
            on_event=on_event,
            settings=self.settings,
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
            o for o in run_result.observations if o.source == "tool" and o.name == "test.run"
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
        """Hidden test contents remain outside the Agent workspace and its observations."""
        from devpilot.evals.benchmark import (
            has_behavior_assertions,
            resource_root,
            run_independent_suite,
        )

        if not has_behavior_assertions(self.hidden_tests_dir / issue_id):
            return {
                "status": "NOT_EVALUATED",
                "passed": False,
                "pass_rate": None,
                "details": "Missing or placeholder hidden tests",
            }
        suite = run_independent_suite(
            Path(sandbox.get_repo_path(run_id)),
            self.hidden_tests_dir / issue_id,
            Path(sandbox.get_runs_dir(run_id)) / "hidden",
            self.settings.test_python,
            timeout=self.config.test_timeout_seconds,
            trusted_fixtures=self.hidden_tests_dir.resolve()
            == (resource_root() / "hidden_tests").resolve(),
        )
        total = suite.passed + suite.failed
        return {
            **suite.model_dump(),
            "passed_count": suite.passed,
            "passed": suite.status == "PASS" and not suite.skipped,
            "pass_rate": suite.passed / total if total else None,
            "details": suite.reason or f"{suite.passed} passed, {suite.failed} failed",
        }

    def _load_state(self, run_id: str, sandbox: SandboxWorkspace) -> DevPilotState:
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

    def _collect_metrics(self, run_result: AgentRunResult, state: DevPilotState) -> dict:
        """Collect metrics from run result and state."""
        tool_calls = sum(1 for o in run_result.observations if o.source == "tool")
        tool_failures = sum(
            1 for o in run_result.observations if o.source == "tool" and not o.success
        )
        return {
            "total_steps": run_result.total_steps,
            "tool_calls": tool_calls,
            "tool_failures": tool_failures,
            "test_retries": state.retry_count,
            "modified_files": len(run_result.modified_files),
            "duration_ms": run_result.duration_ms or 0,
        }

    def _save_final_diff(self, run_id: str, sandbox: SandboxWorkspace) -> str:
        """Get git diff from workspace and save as final.diff artifact."""
        saved = Path(sandbox.get_runs_dir(run_id)) / "final.diff"
        if saved.is_file():
            return saved.read_text(encoding="utf-8")
        workspace_repo = Path(sandbox.get_repo_path(run_id))
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD", "--no-color"],
                cwd=str(workspace_repo),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            diff = result.stdout
        except (OSError, subprocess.SubprocessError):
            diff = ""
        sandbox.save_artifact(run_id, "final.diff", diff)
        return diff

    def _calculate_change_scope(self, run_result: AgentRunResult, diff: str) -> dict:
        """Calculate the scope of changes (files and lines)."""
        files = len(run_result.modified_files)
        lines = 0
        if diff:
            for line in diff.splitlines():
                if (line.startswith("+") and not line.startswith("+++")) or (
                    line.startswith("-") and not line.startswith("---")
                ):
                    lines += 1
        return {"files": files, "lines": lines}

    def generate_summary(self, results: list[EvalResult]) -> str:
        """Generate a summary table of all eval results."""
        if not results:
            return "No evaluation results to display."

        lines: list[str] = []
        header = (
            f"{'Issue':<10} {'Mode':<12} {'Outcome':<8} "
            f"{'Visible%':<10} {'Hidden%':<10} {'Steps':<6} "
            f"{'Retries':<8} {'Duration':<10}"
        )
        lines.append(header)
        lines.append("-" * len(header))

        for r in results:
            visible_pct = (
                f"{r.visible_test_pass_rate * 100:.0f}%"
                if r.visible_test_pass_rate is not None
                else "N/A"
            )
            hidden_pct = (
                f"{r.hidden_test_pass_rate * 100:.0f}%"
                if r.hidden_test_pass_rate is not None
                else "N/A"
            )
            duration = f"{r.runtime_duration_ms}ms"
            success = r.evaluation_status
            lines.append(
                f"{r.issue_id:<10} {r.evaluation_mode:<12} {success:<8} "
                f"{visible_pct:<10} {hidden_pct:<10} "
                f"{r.avg_steps:<6} {r.avg_test_retries:<8} "
                f"{duration:<10}"
            )

        total = len(results)
        capability = [r for r in results if r.evaluation_mode == "capability"]
        counts = {status: sum(r.evaluation_status == status for r in capability)
                  for status in ("PASS", "FAIL", "NOT_EVALUATED", "ERROR")}
        valid = counts["PASS"] + counts["FAIL"]
        lines.append("-" * len(header))
        lines.append(f"Total: {total}, Capability success: {counts['PASS']}; "
                     f"FAIL: {counts['FAIL']}; NOT_EVALUATED: {counts['NOT_EVALUATED']}; "
                     f"ERROR: {counts['ERROR']}")
        lines.append(f"Capability coverage: {valid}/{len(capability)}; "
                     f"Smoke runs: {total - len(capability)} (excluded from capability success)")
        return "\n".join(lines)

    def generate_comparison_table(self, results: list[EvalResult]) -> str:
        """Generate a markdown comparison table."""
        if not results:
            return "No results to compare."

        lines: list[str] = []
        lines.append("| Issue | Mode | Outcome | Visible% | Hidden% | Steps | Retries | Duration |")
        lines.append(
            "|-------|--------|---------|----------|---------|-------|---------|----------|"
        )
        for r in results:
            visible_pct = (
                f"{r.visible_test_pass_rate * 100:.0f}%"
                if r.visible_test_pass_rate is not None
                else "N/A"
            )
            hidden_pct = (
                f"{r.hidden_test_pass_rate * 100:.0f}%"
                if r.hidden_test_pass_rate is not None
                else "N/A"
            )
            duration = f"{r.runtime_duration_ms}ms"
            success = r.evaluation_status
            lines.append(
                f"| {r.issue_id} | {r.evaluation_mode} | {success} | "
                f"{visible_pct} | {hidden_pct} | "
                f"{r.avg_steps} | {r.avg_test_retries} | {duration} |"
            )
        return "\n".join(lines)


def _first_int(pattern: re.Pattern[str], text: str) -> int | None:
    """Return the first integer matched by *pattern* in *text*."""
    m = pattern.search(text)
    return int(m.group(1)) if m else None
