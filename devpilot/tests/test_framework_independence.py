"""Framework independence tests.

Verify that business layers (domain, tools, verification, evals) don't
depend on the custom runtime implementation (``devpilot.runtime.custom``).

Audit findings:
  - domain/   -- no runtime imports (independent)
  - tools/    -- no runtime imports (independent)
  - workspace/ -- no runtime imports (independent)
  - verification/ -- imports ``RuntimeConfig`` from ``devpilot.runtime.base``
    (abstract interface, acceptable); does NOT import ``runtime.custom``
  - evals/    -- imports ``CustomAgentRunner`` from
    ``devpilot.runtime.custom.runner`` (known coupling, xfail)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _import_and_check_runtime(import_stmt: str) -> set[str]:
    """Import a module in a fresh Python process.

    Returns the set of ``devpilot.runtime`` submodules that get loaded
    as a side effect of the import.
    """
    code = (
        f"{import_stmt}\n"
        "import sys\n"
        "mods = sorted(k for k in sys.modules"
        " if k.startswith('devpilot.runtime'))\n"
        "print('\\n'.join(mods))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        pytest.fail(
            f"Import failed: {import_stmt}\n{result.stderr.strip()}"
        )
    return {m for m in result.stdout.splitlines() if m.strip()}


class TestDomainIndependence:
    """Domain models must not import any runtime modules."""

    def test_state_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "import devpilot.domain.state"
        )

    def test_task_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "import devpilot.domain.task"
        )

    def test_decision_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "import devpilot.domain.decision"
        )

    def test_result_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "import devpilot.domain.result"
        )

    def test_plan_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "import devpilot.domain.plan"
        )


class TestToolsIndependence:
    """Tools must not import any runtime modules."""

    def test_registry_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "import devpilot.tools.registry"
        )

    def test_repo_tools_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "from devpilot.tools.repo import ListFiles, ReadFile, SearchCode"
        )

    def test_code_tools_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "from devpilot.tools.code import ApplyPatch, CreateFile"
        )

    def test_git_tools_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "from devpilot.tools.git import GitDiff, GitStatus"
        )

    def test_test_tool_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "from devpilot.tools.test import RunTests"
        )


class TestWorkspaceIndependence:
    """Workspace must not import any runtime modules."""

    def test_sandbox_no_runtime(self) -> None:
        assert not _import_and_check_runtime(
            "from devpilot.workspace.sandbox import SandboxWorkspace"
        )


class TestVerifierIndependence:
    """Verifier must not depend on the custom runtime implementation.

    The verifier may use ``devpilot.runtime.base`` (abstract config) but
    must not import ``devpilot.runtime.custom`` (the implementation).
    """

    def test_verifier_no_custom_runtime(self) -> None:
        runtime_mods = _import_and_check_runtime(
            "from devpilot.verification import TaskVerifier"
        )
        custom_mods = {m for m in runtime_mods if "custom" in m}
        assert not custom_mods, (
            f"Verifier depends on custom runtime: {custom_mods}"
        )


class TestEvalRunnerIndependence:
    """Eval runner currently depends on the custom runtime.

    This is a known coupling: ``evals/runner.py`` directly imports
    ``CustomAgentRunner`` from ``devpilot.runtime.custom.runner``.
    """

    @pytest.mark.xfail(
        reason="evals/runner.py imports CustomAgentRunner from "
        "devpilot.runtime.custom.runner (known coupling)",
        strict=True,
    )
    def test_eval_runner_no_custom_runtime(self) -> None:
        runtime_mods = _import_and_check_runtime(
            "from devpilot.evals.runner import EvalRunner"
        )
        custom_mods = {m for m in runtime_mods if "custom" in m}
        assert not custom_mods, (
            f"Eval runner depends on custom runtime: {custom_mods}"
        )
