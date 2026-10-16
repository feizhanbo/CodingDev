"""Adversarial tests for trusted baseline preservation and complete diffs."""

from __future__ import annotations

import pytest

from devpilot.domain.decision import ToolAction
from devpilot.domain.state import DevPilotState
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.code.apply_patch import ApplyPatch
from devpilot.tools.code.create_file import CreateFile
from devpilot.tools.context import ToolContext
from devpilot.tools.registry import ToolRegistry
from devpilot.tools.test.run_tests import RunTests
from devpilot.verification.evidence import capture_snapshot, materialize_candidate
from devpilot.verification.verifier import TaskVerifier


@pytest.fixture
def evidence(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calculator.py").write_text("def add(a, b): return 0\n", encoding="utf-8")
    (repo / "test_calculator.py").write_text(
        "from calculator import add\ndef test_add(): assert add(3, 4) == 7\n", encoding="utf-8"
    )
    artifacts = tmp_path / "artifacts"
    trusted = capture_snapshot(repo, artifacts)
    return repo, artifacts, trusted


@pytest.mark.parametrize(
    "path", ["conftest.py", "tests/conftest.py", "pytest.ini", "pyproject.toml"]
)
async def test_cannot_create_pytest_configuration(evidence, path):
    repo, artifacts, trusted = evidence
    tool = CreateFile()
    result = await tool.execute(
        tool.input_model(path=path, content=""),
        ToolContext(workspace_root=str(repo), run_id="case", trusted_root=str(trusted)),
    )
    assert not result.success
    assert "Protected" in result.error
    assert not (repo / path).exists()


async def test_cannot_patch_frozen_tests(evidence):
    repo, artifacts, trusted = evidence
    registry = ToolRegistry()
    registry.register(ApplyPatch())
    action = ToolAction(
        tool="code.apply_patch",
        arguments={
            "patch": "--- a/test_calculator.py\n+++ b/test_calculator.py\n@@ -1,2 +1,2 @@\n"
            " from calculator import add\n-def test_add(): assert add(3, 4) == 7\n"
            "+def test_add(): assert True\n"
        },
    )
    result = await registry.execute(
        action, ToolContext(workspace_root=str(repo), run_id="case", trusted_root=str(trusted))
    )
    assert not result.success
    assert "Protected baseline test" in result.error
    assert "== 7" in (repo / "test_calculator.py").read_text(encoding="utf-8")


def test_deleted_baseline_test_rejected_even_if_state_omits_it(evidence):
    repo, artifacts, trusted = evidence
    (repo / "test_calculator.py").unlink()
    with pytest.raises(PermissionError, match="Protected tests"):
        materialize_candidate(repo, trusted, artifacts)


def test_untracked_new_file_in_exported_diff(evidence):
    repo, artifacts, trusted = evidence
    (repo / "feature.py").write_text("new_feature = 7\n", encoding="utf-8")
    _, diff, changed = materialize_candidate(repo, trusted, artifacts)
    assert "feature.py" in changed
    assert "+new_feature = 7" in diff
    assert "b/feature.py" in diff


async def test_trivial_added_test_cannot_hide_broken_baseline(evidence):
    repo, artifacts, trusted = evidence
    (repo / "test_trivial.py").write_text("def test_trivial(): assert True\n", encoding="utf-8")
    verifier = TaskVerifier(RuntimeConfig())
    verifier.bind_snapshot("case", trusted)
    registry = ToolRegistry()
    registry.register(RunTests())
    task = DevelopmentTask(id="case", title="Addition", description="", acceptance_criteria=[])
    state = DevPilotState(run_id="case", task=task, phase="verifying")
    result = await verifier.verify(task, str(repo), state, registry)
    assert not result.success
    visible = next(c for c in result.checks if c["name"] == "visible_tests")
    assert not visible["passed"]
    assert visible["result"]["failed"] == 1


async def test_new_tests_and_real_fix_pass(evidence):
    repo, artifacts, trusted = evidence
    (repo / "calculator.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    (repo / "test_zero.py").write_text(
        "from calculator import add\ndef test_zero(): assert add(0, 6) == 6\n", encoding="utf-8"
    )
    verifier = TaskVerifier(RuntimeConfig())
    verifier.bind_snapshot("case", trusted)
    registry = ToolRegistry()
    registry.register(RunTests())
    task = DevelopmentTask(
        id="case", title="Addition", description="", acceptance_criteria=["Must add tests"]
    )
    state = DevPilotState(run_id="case", task=task, phase="verifying")
    result = await verifier.verify(task, str(repo), state, registry)
    assert result.success, result.failure_reason
    assert set(state.modified_files) == {"calculator.py", "test_zero.py"}
    assert (artifacts / "final.diff").is_file()


async def test_unregistered_baseline_fails_closed(evidence):
    repo, _, _ = evidence
    task = DevelopmentTask(id="case", title="Addition", description="", acceptance_criteria=[])
    state = DevPilotState(run_id="case", task=task, phase="verifying")
    result = await TaskVerifier(RuntimeConfig()).verify(task, str(repo), state, ToolRegistry())
    assert not result.success
    assert "Missing trusted baseline" in result.failure_reason
