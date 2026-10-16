"""Behavioral checks for configuration shared by runs and evaluations."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from devpilot.cli import app, initialize_components
from devpilot.domain.decision import AgentDecision, ToolAction
from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.evals.runner import EvalRunner
from devpilot.runtime.custom.loop_guard import GuardrailViolation, LoopGuard
from devpilot.settings import Settings
from devpilot.tools.context import ToolContext, ToolResult
from devpilot.tools.test.run_tests import RunTests


def test_precedence_and_no_secret_snapshot(tmp_path, monkeypatch):
    env = tmp_path / "settings.env"
    env.write_text("DEVPILOT_MAX_STEPS=11\nDEVPILOT_MAX_PATCH_FAILURES=2\n", encoding="utf-8")
    monkeypatch.setenv("DEVPILOT_MAX_STEPS", "12")
    settings = Settings(_env_file=env, max_steps=13, api_key="private-key")
    assert settings.max_steps == 13
    assert Settings(_env_file=env).max_steps == 12
    assert settings.runtime_config().max_patch_failures == 2
    assert "private-key" not in repr(settings)
    assert "private-key" not in str(settings.public_snapshot())


@pytest.mark.parametrize("field,value", [
    ("max_steps", 0), ("max_test_retries", -1), ("max_modified_files", 0),
    ("max_patch_failures", 0), ("test_timeout_seconds", 0),
])
def test_invalid_limits_fail_at_startup(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_runtime_and_eval_use_same_configuration(tmp_path):
    settings = Settings(_env_file=None, max_steps=17, max_modified_files=2,
                        max_patch_failures=2, test_timeout_seconds=9,
                        workspace_root=str(tmp_path / "ws"), runs_root=str(tmp_path / "art"))
    runner = initialize_components(fake=True, settings=settings)
    evaluation = EvalRunner(str(tmp_path), settings=settings)
    assert runner.config == evaluation.config == settings.runtime_config()
    assert runner.sandbox.runs_root == tmp_path / "art"
    assert (evaluation.issues_dir / "DEV-008.yaml").is_file()
    assert (evaluation.hidden_tests_dir / "DEV-002" / "test_hidden_dev002.py").is_file()


def test_patch_failure_limit_is_enforced():
    guard = LoopGuard(Settings(_env_file=None, max_patch_failures=2).runtime_config())
    state = DevPilotState(run_id="budget", phase="implementing", task=DevelopmentTask(
        id="budget", title="budget", description="", acceptance_criteria=[]))
    first = AgentDecision(action=ToolAction(tool="code.apply_patch", arguments={"patch": "a"}))
    second = AgentDecision(action=ToolAction(tool="code.apply_patch", arguments={"patch": "b"}))
    guard.inspect(state, first, ToolResult(success=False))
    with pytest.raises(GuardrailViolation, match="max_patch_failures=2"):
        guard.inspect(state, second, ToolResult(success=False))


async def test_custom_artifacts_and_target_interpreter(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "test_ok.py").write_text("def test_ok(): assert 1 + 1 == 2\n", encoding="utf-8")
    tool = RunTests(python_executable=sys.executable, runs_root=str(tmp_path / "wrong"))
    context = ToolContext(workspace_root=str(repo), run_id="abc",
                          artifacts_dir=str(tmp_path / "actual"))
    first = await tool.execute(tool.input_model(), context)
    second = await tool.execute(tool.input_model(), context)
    assert first.success and second.success
    assert first.data["log_file"] != second.data["log_file"]
    assert Path(first.data["log_file"]).is_relative_to(tmp_path / "actual")
    # An explicit interpreter override must be used, not silently ignored.
    context.test_python = str(tmp_path / "missing-python")
    failure = await tool.execute(tool.input_model(), context)
    assert not failure.success
    assert "Failed to start pytest" in failure.error


def test_inspect_resolves_configured_runs_directory(tmp_path, monkeypatch):
    run = tmp_path / "artifacts" / "example"
    run.mkdir(parents=True)
    (run / "final.diff").write_text("+configuration works\n", encoding="utf-8")
    monkeypatch.setenv("DEVPILOT_RUNS_ROOT", str(run.parent))
    result = CliRunner().invoke(app, ["inspect", "example"])
    assert result.exit_code == 0
    assert "configuration works" in result.output
