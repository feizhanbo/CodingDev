"""Tests for the EvalRunner and eval framework."""

from __future__ import annotations

from pathlib import Path

import pytest

from devpilot.domain.result import AgentRunResult
from devpilot.domain.state import DevPilotState, Observation
from devpilot.domain.task import DevelopmentTask
from devpilot.evals.metrics import collect_metrics
from devpilot.evals.runner import EvalResult, EvalRunner
from devpilot.runtime.base import RuntimeConfig

_ISSUE_YAML = """\
id: DEV-001
title: Test issue for evaluation
description: |
  A test issue for evaluation purposes.
acceptance_criteria:
  - Tests pass
  - Code is modified
constraints: []
"""

_ISSUE2_YAML = """\
id: DEV-002
title: Second test issue
description: |
  Another test issue.
acceptance_criteria:
  - Tests pass
constraints: []
"""

_HIDDEN_TEST = """\
\"\"\"Hidden test for DEV-001.\"\"\"

from __future__ import annotations


def test_hidden_placeholder():
    assert True
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _setup_baseline(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\nz = 3\n")
    _write(base / "test_pass.py", "def test_ok():\n    assert True\n")


def _setup_issues(issues_dir: Path) -> None:
    issues_dir.mkdir(parents=True, exist_ok=True)
    _write(issues_dir / "DEV-001.yaml", _ISSUE_YAML)
    _write(issues_dir / "DEV-002.yaml", _ISSUE2_YAML)


class TestEvalResultModel:
    """Tests for EvalResult model creation and defaults."""

    def test_model_creation(self) -> None:
        result = EvalResult(
            issue_id="DEV-001",
            run_id="run_test",
            task_success=True, evaluation_status="PASS",
            visible_test_pass_rate=1.0,
            hidden_test_pass_rate=1.0,
            avg_steps=4,
            avg_test_retries=0,
            tool_failure_rate=0.0,
            change_scope={"files": 1, "lines": 2},
            runtime_duration_ms=1000,
            agent_status="completed",
        )
        assert result.issue_id == "DEV-001"
        assert result.run_id == "run_test"
        assert result.task_success is True
        assert result.visible_test_pass_rate == 1.0
        assert result.hidden_test_pass_rate == 1.0
        assert result.avg_steps == 4
        assert result.avg_test_retries == 0
        assert result.tool_failure_rate == 0.0
        assert result.change_scope == {"files": 1, "lines": 2}
        assert result.runtime_duration_ms == 1000
        assert result.agent_status == "completed"
        assert result.error is None
        assert result.regression_rate is None
        assert result.token_cost is None

    def test_model_with_defaults(self) -> None:
        result = EvalResult(
            issue_id="DEV-002",
            run_id="run_test2",
            task_success=False, evaluation_status="FAIL",
            visible_test_pass_rate=0.0,
            agent_status="failed",
            error="Max retries exceeded",
        )
        assert result.task_success is False
        assert result.hidden_test_pass_rate is None
        assert result.avg_steps == 0
        assert result.avg_test_retries == 0
        assert result.tool_failure_rate == 0.0
        assert result.change_scope == {}
        assert result.runtime_duration_ms == 0
        assert result.error == "Max retries exceeded"

    def test_model_serialization(self) -> None:
        result = EvalResult(
            issue_id="DEV-003",
            run_id="run_abc",
            task_success=True, evaluation_status="PASS",
            visible_test_pass_rate=0.8,
            hidden_test_pass_rate=0.5,
            avg_steps=10,
            agent_status="completed",
        )
        json_str = result.model_dump_json()
        assert "DEV-003" in json_str
        assert "run_abc" in json_str
        assert "0.8" in json_str

        restored = EvalResult.model_validate_json(json_str)
        assert restored.issue_id == "DEV-003"
        assert restored.visible_test_pass_rate == 0.8


class TestRunEval:
    """Tests for EvalRunner.run_eval with FakeLLMClient."""

    async def test_run_eval_with_fake_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)
        issues_dir = tmp_path / "issues"
        _setup_issues(issues_dir)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        config = RuntimeConfig(max_steps=30)
        runner = EvalRunner(
            base_repo_path=str(baseline),
            issues_dir=str(issues_dir),
            hidden_tests_dir=str(tmp_path / "hidden_tests"),
            config=config,
        )

        result = await runner.run_eval("DEV-001", fake=True)

        assert result.issue_id == "DEV-001"
        assert result.agent_status == "completed"
        assert result.task_success is None
        assert result.evaluation_mode == "smoke"
        assert result.evaluation_status == "PASS"
        assert result.visible_test_pass_rate == 1.0
        assert result.avg_steps > 0
        assert result.error is None
        assert result.run_id.startswith("run_")

        runs_dir = tmp_path / "runs" / result.run_id
        assert (runs_dir / "eval_result.json").is_file()
        assert (runs_dir / "state.json").is_file()
        assert (runs_dir / "result.json").is_file()
        assert (runs_dir / "final.diff").is_file()

    async def test_run_eval_no_hidden_tests(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)
        issues_dir = tmp_path / "issues"
        _setup_issues(issues_dir)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        runner = EvalRunner(
            base_repo_path=str(baseline),
            issues_dir=str(issues_dir),
            hidden_tests_dir=str(tmp_path / "hidden_tests"),
        )
        result = await runner.run_eval("DEV-001", fake=True)

        assert result.hidden_test_pass_rate is None
        assert result.task_success is None
        assert result.evaluation_mode == "smoke"
        assert result.evaluation_status == "PASS"

    async def test_run_eval_with_hidden_tests(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)
        issues_dir = tmp_path / "issues"
        _setup_issues(issues_dir)

        hidden_dir = tmp_path / "hidden_tests" / "DEV-001"
        _write(hidden_dir / "test_hidden_dev001.py", _HIDDEN_TEST)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        runner = EvalRunner(
            base_repo_path=str(baseline),
            issues_dir=str(issues_dir),
            hidden_tests_dir=str(tmp_path / "hidden_tests"),
        )
        result = await runner.run_eval("DEV-001", fake=True)

        assert result.hidden_test_pass_rate is None
        assert result.task_success is None
        assert result.evaluation_mode == "smoke"
        assert result.evaluation_status == "PASS"

    async def test_run_eval_saves_change_scope(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)
        issues_dir = tmp_path / "issues"
        _setup_issues(issues_dir)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        runner = EvalRunner(
            base_repo_path=str(baseline),
            issues_dir=str(issues_dir),
            hidden_tests_dir=str(tmp_path / "hidden_tests"),
        )
        result = await runner.run_eval("DEV-001", fake=True)

        assert result.change_scope["files"] > 0
        assert result.change_scope["lines"] > 0


class TestRunAll:
    """Tests for EvalRunner.run_all."""

    async def test_run_all_loads_all_issues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)
        issues_dir = tmp_path / "issues"
        _setup_issues(issues_dir)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        runner = EvalRunner(
            base_repo_path=str(baseline),
            issues_dir=str(issues_dir),
            hidden_tests_dir=str(tmp_path / "hidden_tests"),
        )
        results = await runner.run_all(fake=True)

        assert len(results) == 2
        issue_ids = [r.issue_id for r in results]
        assert "DEV-001" in issue_ids
        assert "DEV-002" in issue_ids
        for r in results:
            assert r.agent_status == "completed"


class TestHiddenTestsIsolation:
    """Tests for hidden tests isolation."""

    async def test_hidden_tests_outside_workspace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)
        issues_dir = tmp_path / "issues"
        _setup_issues(issues_dir)

        hidden_dir = tmp_path / "hidden_tests" / "DEV-001"
        _write(hidden_dir / "test_hidden.py", _HIDDEN_TEST)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        runner = EvalRunner(
            base_repo_path=str(baseline),
            issues_dir=str(issues_dir),
            hidden_tests_dir=str(tmp_path / "hidden_tests"),
        )
        result = await runner.run_eval("DEV-001", fake=True)

        # Hidden tests dir is not inside the workspace root
        hidden_tests_resolved = (tmp_path / "hidden_tests").resolve()
        workspace_root = (tmp_path / "workspaces").resolve()
        assert not str(hidden_tests_resolved).startswith(
            str(workspace_root)
        )

        # Hidden tests were copied to workspace after the run
        workspace_hidden = (
            tmp_path / "workspaces" / result.run_id / "repo" / "hidden_tests"
        )
        assert not workspace_hidden.exists()

    async def test_hidden_tests_not_accessible_during_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify hidden test files are not in workspace during agent run."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)
        issues_dir = tmp_path / "issues"
        _setup_issues(issues_dir)

        hidden_dir = tmp_path / "hidden_tests" / "DEV-001"
        _write(hidden_dir / "test_secret.py", _HIDDEN_TEST)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))

        # Track workspace state during agent run
        workspace_hidden_during_run: list[bool] = []

        original_init = EvalRunner._init_components

        def tracking_init(
            self: EvalRunner,
            fake: bool = False,
            on_event=None,
        ):
            runner = original_init(self, fake=fake, on_event=on_event)

            # Check workspace before run starts
            from devpilot.workspace.config import WorkspaceConfig

            ws_config = WorkspaceConfig()
            ws_root = Path(ws_config.workspace_root)
            # No hidden_tests should exist yet in any workspace
            for _child in ws_root.glob("*/repo/hidden_tests"):
                workspace_hidden_during_run.append(True)
            if not workspace_hidden_during_run:
                workspace_hidden_during_run.append(False)

            return runner

        monkeypatch.setattr(EvalRunner, "_init_components", tracking_init)

        runner = EvalRunner(
            base_repo_path=str(baseline),
            issues_dir=str(issues_dir),
            hidden_tests_dir=str(tmp_path / "hidden_tests"),
        )
        await runner.run_eval("DEV-001", fake=True)

        # Hidden tests should NOT have been in workspace during run
        assert not workspace_hidden_during_run[0]


class TestMetricsCollection:
    """Tests for metrics collection."""

    def test_collect_metrics_basic(self) -> None:
        task = DevelopmentTask(
            id="DEV-001",
            title="Test",
            description="desc",
            acceptance_criteria=["criterion"],
        )
        state = DevPilotState(
            run_id="run_test",
            task=task,
            phase="completed",
            total_steps=5,
            retry_count=1,
            modified_files=["app.py"],
            observations=[
                Observation(
                    step_id=1,
                    source="tool",
                    name="repo.search_code",
                    success=True,
                    summary="OK",
                ),
                Observation(
                    step_id=2,
                    source="tool",
                    name="code.apply_patch",
                    success=True,
                    summary="patch applied",
                ),
                Observation(
                    step_id=3,
                    source="tool",
                    name="test.run",
                    success=False,
                    summary="tests failed",
                ),
            ],
        )
        run_result = AgentRunResult(
            run_id="run_test",
            task_id="DEV-001",
            status="completed",
            phase="completed",
            total_steps=5,
            modified_files=["app.py"],
            observations=state.observations,
            duration_ms=5000,
        )

        metrics = collect_metrics(run_result, state)

        assert metrics["total_steps"] == 5
        assert metrics["tool_calls"] == 3
        assert metrics["tool_failures"] == 1
        assert metrics["test_retries"] == 1
        assert metrics["modified_files"] == 1
        assert metrics["duration_ms"] == 5000

    def test_collect_metrics_empty(self) -> None:
        task = DevelopmentTask(
            id="DEV-002",
            title="Test",
            description="desc",
            acceptance_criteria=[],
        )
        state = DevPilotState(
            run_id="run_empty",
            task=task,
            phase="failed",
        )
        run_result = AgentRunResult(
            run_id="run_empty",
            task_id="DEV-002",
            status="failed",
            phase="failed",
            total_steps=0,
        )

        metrics = collect_metrics(run_result, state)

        assert metrics["total_steps"] == 0
        assert metrics["tool_calls"] == 0
        assert metrics["tool_failures"] == 0
        assert metrics["test_retries"] == 0
        assert metrics["modified_files"] == 0
        assert metrics["duration_ms"] == 0

    def test_eval_runner_collect_metrics(self) -> None:
        """Test the EvalRunner._collect_metrics method."""
        runner = EvalRunner(
            base_repo_path=".",
            issues_dir=".",
            hidden_tests_dir=".",
        )
        task = DevelopmentTask(
            id="DEV-001",
            title="Test",
            description="desc",
            acceptance_criteria=[],
        )
        state = DevPilotState(
            run_id="run_test",
            task=task,
            phase="completed",
            total_steps=4,
            retry_count=2,
            modified_files=["app.py", "config.py"],
        )
        run_result = AgentRunResult(
            run_id="run_test",
            task_id="DEV-001",
            status="completed",
            phase="completed",
            total_steps=4,
            modified_files=["app.py", "config.py"],
            observations=[
                Observation(
                    step_id=1,
                    source="tool",
                    name="repo.search_code",
                    success=True,
                    summary="OK",
                ),
                Observation(
                    step_id=2,
                    source="tool",
                    name="code.apply_patch",
                    success=False,
                    summary="failed",
                ),
            ],
            duration_ms=3000,
        )

        metrics = runner._collect_metrics(run_result, state)

        assert metrics["total_steps"] == 4
        assert metrics["tool_calls"] == 2
        assert metrics["tool_failures"] == 1
        assert metrics["test_retries"] == 2
        assert metrics["modified_files"] == 2
        assert metrics["duration_ms"] == 3000


class TestSummaryGeneration:
    """Tests for summary and comparison table generation."""

    def test_generate_summary_empty(self) -> None:
        runner = EvalRunner(base_repo_path=".")
        summary = runner.generate_summary([])
        assert "No evaluation results" in summary

    def test_generate_summary_with_results(self) -> None:
        runner = EvalRunner(base_repo_path=".")
        results = [
            EvalResult(
                issue_id="DEV-001",
                run_id="run_1",
                task_success=True, evaluation_status="PASS",
                visible_test_pass_rate=1.0,
                hidden_test_pass_rate=1.0,
                avg_steps=4,
                avg_test_retries=0,
                runtime_duration_ms=1000,
                agent_status="completed",
            ),
            EvalResult(
                issue_id="DEV-002",
                run_id="run_2",
                task_success=False, evaluation_status="FAIL",
                visible_test_pass_rate=0.5,
                hidden_test_pass_rate=None,
                avg_steps=10,
                avg_test_retries=2,
                runtime_duration_ms=5000,
                agent_status="failed",
                error="Max retries exceeded",
            ),
        ]
        summary = runner.generate_summary(results)
        assert "DEV-001" in summary
        assert "DEV-002" in summary
        assert "Total: 2" in summary
        assert "Capability success: 1" in summary
        assert "FAIL: 1" in summary

    def test_generate_comparison_table_empty(self) -> None:
        runner = EvalRunner(base_repo_path=".")
        table = runner.generate_comparison_table([])
        assert "No results" in table

    def test_generate_comparison_table_with_results(self) -> None:
        runner = EvalRunner(base_repo_path=".")
        results = [
            EvalResult(
                issue_id="DEV-001",
                run_id="run_1",
                task_success=True, evaluation_status="PASS",
                visible_test_pass_rate=1.0,
                hidden_test_pass_rate=1.0,
                avg_steps=4,
                avg_test_retries=0,
                runtime_duration_ms=1000,
                agent_status="completed",
            ),
        ]
        table = runner.generate_comparison_table(results)
        assert "DEV-001" in table
        assert "capability" in table
        assert "PASS" in table
        assert "PASS" in table
        assert "100%" in table
        assert "|" in table
