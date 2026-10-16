"""End-to-end evaluator outcomes using a deterministic repair, never a paid model."""

from __future__ import annotations

from pathlib import Path

import pytest

from devpilot.cli import initialize_components
from devpilot.evals.runner import EvalRunner
from devpilot.settings import Settings


@pytest.mark.parametrize(
    "test_code,status,success",
    [
        ("from calculator import add\ndef test_hidden(): assert add(53, -2) == 51\n", "PASS", True),
        (
            "from calculator import add\ndef test_hidden(): assert add(53, -2) == 99\n",
            "FAIL",
            False,
        ),
        (None, "NOT_EVALUATED", None),
        ("def test_placeholder(): assert True\n", "NOT_EVALUATED", None),
        ("def test_hidden(missing_fixture): assert missing_fixture == 1\n", "ERROR", None),
    ],
)
async def test_capability_verdict_requires_trusted_evidence(
    tmp_path, monkeypatch, test_code, status, success
):
    issues = tmp_path / "issues"
    issues.mkdir()
    (issues / "DEV-001.yaml").write_text(
        "id: DEV-001\ntitle: Add\ndescription: Fix addition\n"
        "acceptance_criteria: [Must add tests]\n",
        encoding="utf-8",
    )
    hidden = tmp_path / "hidden"
    if test_code is not None:
        (hidden / "DEV-001").mkdir(parents=True)
        (hidden / "DEV-001/test_hidden.py").write_text(test_code, encoding="utf-8")
    settings = Settings(
        _env_file=None, workspace_root=str(tmp_path / "ws"), runs_root=str(tmp_path / "runs")
    )
    evaluator = EvalRunner(
        str(tmp_path), issues_dir=str(issues), hidden_tests_dir=str(hidden), settings=settings
    )
    # Inject a scripted model at the composition boundary, while exercising all
    # production capability evidence collection and verdict logic.
    monkeypatch.setattr(
        evaluator,
        "_init_components",
        lambda **kwargs: initialize_components(fake=True, settings=settings),
    )
    result = await evaluator.run_eval("DEV-001", fake=False)
    assert result.evaluation_status == status, result
    assert result.task_success is success
    assert result.evaluation_mode == "capability"
    assert result.visible_test_pass_rate == 1.0
    assert not (Path(settings.workspace_root) / result.run_id / "repo/hidden_tests").exists()
    saved = Path(settings.runs_root) / result.run_id / "eval_result.json"
    assert saved.is_file()


async def test_bad_issue_preserves_error_artifact(tmp_path):
    settings = Settings(_env_file=None, runs_root=str(tmp_path / "runs"))
    evaluator = EvalRunner(str(tmp_path), issues_dir=str(tmp_path), settings=settings)
    result = await evaluator.run_eval("MISSING")
    assert result.evaluation_status == "ERROR"
    assert result.task_success is None
    assert (Path(settings.runs_root) / result.run_id / "eval_result.json").is_file()
