"""Tests for DEV-002~005 issue YAML files."""

from __future__ import annotations

from pathlib import Path

import pytest

from devpilot.cli import load_issue
from devpilot.domain.task import DevelopmentTask

_ISSUES_DIR = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "issues"
)

_ISSUE_IDS = ["DEV-002", "DEV-003", "DEV-004", "DEV-005"]


class TestLoadDevIssues:
    """Test that DEV-002~005 YAML files can be loaded."""

    @pytest.mark.parametrize("issue_id", _ISSUE_IDS)
    def test_loads_into_development_task(self, issue_id: str) -> None:
        path = _ISSUES_DIR / f"{issue_id}.yaml"
        task = load_issue(str(path))
        assert isinstance(task, DevelopmentTask)
        assert task.id == issue_id

    @pytest.mark.parametrize("issue_id", _ISSUE_IDS)
    def test_acceptance_criteria_non_empty(self, issue_id: str) -> None:
        path = _ISSUES_DIR / f"{issue_id}.yaml"
        task = load_issue(str(path))
        assert len(task.acceptance_criteria) > 0

    @pytest.mark.parametrize("issue_id", _ISSUE_IDS)
    def test_constraints_present(self, issue_id: str) -> None:
        path = _ISSUES_DIR / f"{issue_id}.yaml"
        task = load_issue(str(path))
        assert len(task.constraints) > 0

    @pytest.mark.parametrize("issue_id", _ISSUE_IDS)
    def test_metadata_contains_issue_file(self, issue_id: str) -> None:
        path = _ISSUES_DIR / f"{issue_id}.yaml"
        task = load_issue(str(path))
        assert "issue_file" in task.metadata

    def test_dev002_title_and_description(self) -> None:
        task = load_issue(str(_ISSUES_DIR / "DEV-002.yaml"))
        assert task.title == "Prevent invalid order cancellation"
        assert "cancelled" in task.description

    def test_dev003_title_and_description(self) -> None:
        task = load_issue(str(_ISSUES_DIR / "DEV-003.yaml"))
        assert task.title == "Fix order pagination edge case"
        assert "page" in task.description

    def test_dev004_title_and_description(self) -> None:
        task = load_issue(str(_ISSUES_DIR / "DEV-004.yaml"))
        assert task.title == "Fix percentage coupon calculation error"
        assert "percentage" in task.description

    def test_dev005_title_and_description(self) -> None:
        task = load_issue(str(_ISSUES_DIR / "DEV-005.yaml"))
        assert task.title == "Optimize order detail N+1 query"
        assert "N+1" in task.description

    def test_dev002_specific_criteria(self) -> None:
        task = load_issue(str(_ISSUES_DIR / "DEV-002.yaml"))
        assert any("409" in c for c in task.acceptance_criteria)
        assert any("shipped" in c for c in task.acceptance_criteria)

    def test_dev003_specific_criteria(self) -> None:
        task = load_issue(str(_ISSUES_DIR / "DEV-003.yaml"))
        assert any("400" in c for c in task.acceptance_criteria)

    def test_dev004_specific_criteria(self) -> None:
        task = load_issue(str(_ISSUES_DIR / "DEV-004.yaml"))
        assert any("100" in c for c in task.acceptance_criteria)

    def test_dev005_specific_criteria(self) -> None:
        task = load_issue(str(_ISSUES_DIR / "DEV-005.yaml"))
        assert any("500ms" in c for c in task.acceptance_criteria)
