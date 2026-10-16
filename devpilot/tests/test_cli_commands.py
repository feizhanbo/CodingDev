"""Tests for CLI inspect/diff/eval commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devpilot.cli import app
from devpilot.evals.runner import EvalResult, EvalRunner

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _setup_baseline(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    _write(base / "app.py", "x = 1\nz = 3\n")
    _write(base / "test_pass.py", "def test_ok():\n    assert True\n")


def _create_mock_run(runs_dir: Path, run_id: str) -> str:
    """Create mock run artifacts in runs_dir/{run_id}/."""
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    state_data = {
        "run_id": run_id,
        "task": {
            "id": "DEV-001",
            "title": "Test issue",
            "description": "desc",
            "acceptance_criteria": ["Tests pass"],
            "constraints": [],
            "metadata": {},
        },
        "phase": "completed",
        "observations": [
            {
                "step_id": 1,
                "source": "tool",
                "name": "repo.search_code",
                "success": True,
                "summary": "OK",
                "data": None,
                "duration_ms": 10,
            }
        ],
        "modified_files": ["app.py"],
        "current_step": 4,
        "total_steps": 4,
        "retry_count": 0,
        "completion_requested": True,
    }
    _write(run_dir / "state.json", json.dumps(state_data, indent=2))

    result_data = {
        "run_id": run_id,
        "task_id": "DEV-001",
        "status": "completed",
        "phase": "completed",
        "total_steps": 4,
        "modified_files": ["app.py"],
        "observations": [],
        "final_diff": None,
        "summary": "Changes applied",
        "risk": "low",
        "duration_ms": 1000,
        "error": None,
        "metrics": {
            "total_steps": 4,
            "tool_calls": 3,
            "tool_failure_rate": 0.0,
            "test_retries": 0,
            "modified_files": 1,
            "duration_ms": 1000,
            "tokens": 0,
            "finish_rejected_count": 0,
        },
    }
    _write(run_dir / "result.json", json.dumps(result_data, indent=2))

    trace_lines = [
        json.dumps({
            "run_id": run_id, "step": 0,
            "phase": "understanding", "event": "run_started",
        }),
        json.dumps({
            "run_id": run_id, "step": 1,
            "phase": "exploring", "event": "tool_call",
            "tool": "repo.search_code",
        }),
        json.dumps({
            "run_id": run_id, "step": 4,
            "phase": "completed", "event": "run_completed",
        }),
    ]
    _write(run_dir / "trace.jsonl", "\n".join(trace_lines) + "\n")

    diff_content = (
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,2 +1,3 @@\n"
        " x = 1\n"
        "+y = 2\n"
        " z = 3\n"
    )
    _write(run_dir / "final.diff", diff_content)

    return run_id


class TestInspectCommand:
    """Tests for the inspect CLI command."""

    def test_inspect_help(self) -> None:
        """Inspect command shows help."""
        runner = CliRunner()
        result = runner.invoke(app, ["inspect", "--help"])
        assert result.exit_code == 0
        assert "inspect" in result.output.lower()

    def test_inspect_not_found(self, tmp_path: Path) -> None:
        """Inspect returns error for non-existent run."""
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["inspect", "run_nonexistent", "--runs-dir", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_inspect_shows_run_info(self, tmp_path: Path) -> None:
        """Inspect displays state, result, and trace info."""
        runs_dir = tmp_path / "runs"
        run_id = _create_mock_run(runs_dir, "run_test123")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["inspect", run_id, "--runs-dir", str(runs_dir)],
        )
        assert result.exit_code == 0
        assert "run_test123" in result.output
        assert "completed" in result.output
        assert "app.py" in result.output
        assert "Total events: 3" in result.output

    def test_inspect_shows_trace_key_events(self, tmp_path: Path) -> None:
        """Inspect shows key trace events."""
        runs_dir = tmp_path / "runs"
        run_id = _create_mock_run(runs_dir, "run_trace_test")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["inspect", run_id, "--runs-dir", str(runs_dir)],
        )
        assert result.exit_code == 0
        assert "run_started" in result.output
        assert "run_completed" in result.output

    def test_inspect_shows_diff(self, tmp_path: Path) -> None:
        """Inspect shows final diff if present."""
        runs_dir = tmp_path / "runs"
        run_id = _create_mock_run(runs_dir, "run_diff_test")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["inspect", run_id, "--runs-dir", str(runs_dir)],
        )
        assert result.exit_code == 0
        assert "Diff" in result.output or "app.py" in result.output


class TestDiffCommand:
    """Tests for the diff CLI command."""

    def test_diff_help(self) -> None:
        """Diff command shows help."""
        runner = CliRunner()
        result = runner.invoke(app, ["diff", "--help"])
        assert result.exit_code == 0
        assert "diff" in result.output.lower()

    def test_diff_not_found(self, tmp_path: Path) -> None:
        """Diff returns error when no diff found."""
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["diff", "run_nonexistent", "--runs-dir", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "No diff found" in result.output

    def test_diff_shows_changes(self, tmp_path: Path) -> None:
        """Diff displays the final diff content."""
        runs_dir = tmp_path / "runs"
        run_id = _create_mock_run(runs_dir, "run_diff123")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["diff", run_id, "--runs-dir", str(runs_dir)],
        )
        assert result.exit_code == 0
        assert "app.py" in result.output
        assert "y = 2" in result.output

    def test_diff_empty_file(self, tmp_path: Path) -> None:
        """Diff handles empty final.diff gracefully."""
        runs_dir = tmp_path / "runs"
        run_dir = runs_dir / "run_empty_diff"
        run_dir.mkdir(parents=True, exist_ok=True)
        _write(run_dir / "final.diff", "")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["diff", "run_empty_diff", "--runs-dir", str(runs_dir)],
        )
        assert result.exit_code == 1


class TestEvalCommand:
    """Tests for the eval CLI command."""

    def test_eval_help(self) -> None:
        """Eval command shows help."""
        runner = CliRunner()
        result = runner.invoke(app, ["eval", "--help"])
        assert result.exit_code == 0
        assert "eval" in result.output.lower()

    def test_eval_no_args(self) -> None:
        """Eval without args or --all shows error."""
        runner = CliRunner()
        result = runner.invoke(app, ["eval"])
        assert result.exit_code == 1
        assert "issue ID" in result.output or "--all" in result.output

    def test_eval_single_issue(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Eval runs a single issue with fake LLM."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))
        monkeypatch.chdir(_PROJECT_ROOT)

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "eval",
                "DEV-001",
                "--fake",
                "--base-repo",
                str(baseline),
            ],
        )
        assert result.exit_code == 0
        assert "DEV-001" in result.output

    def test_eval_all(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Eval --all runs all issues (mocked)."""
        baseline = tmp_path / "baseline"
        _setup_baseline(baseline)

        monkeypatch.setenv(
            "DEVPILOT_WORKSPACE_ROOT", str(tmp_path / "workspaces")
        )
        monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(tmp_path / "runs"))
        monkeypatch.chdir(_PROJECT_ROOT)

        # Mock run_all to avoid running all 8 issues
        async def mock_run_all(
            self: EvalRunner,
            fake: bool = False,
            on_event=None,
        ) -> list[EvalResult]:
            return [
                EvalResult(
                    issue_id="DEV-001",
                    run_id="run_mock1",
                    task_success=None, evaluation_mode="smoke", evaluation_status="PASS",
                    visible_test_pass_rate=1.0,
                    avg_steps=4,
                    runtime_duration_ms=1000,
                    agent_status="completed",
                ),
                EvalResult(
                    issue_id="DEV-002",
                    run_id="run_mock2",
                    task_success=None, evaluation_mode="smoke", evaluation_status="PASS",
                    visible_test_pass_rate=1.0,
                    avg_steps=4,
                    runtime_duration_ms=1000,
                    agent_status="completed",
                ),
            ]

        monkeypatch.setattr(EvalRunner, "run_all", mock_run_all)

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "eval",
                "--all",
                "--fake",
                "--base-repo",
                str(baseline),
            ],
        )
        assert result.exit_code == 0
        assert "DEV-001" in result.output
        assert "DEV-002" in result.output
        assert "Total: 2" in result.output
