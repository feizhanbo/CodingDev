"""Tests for the issue YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from devpilot.cli import load_issue
from devpilot.domain.task import DevelopmentTask

_ISSUE_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "issues"
    / "DEV-001.yaml"
)


class TestLoadIssue:
    def test_loads_dev001(self) -> None:
        task = load_issue(str(_ISSUE_PATH))
        assert isinstance(task, DevelopmentTask)
        assert task.id == "DEV-001"
        assert task.title == "Support order status filter"
        assert "status" in task.description
        assert len(task.acceptance_criteria) == 4
        assert len(task.constraints) == 1

    def test_metadata_contains_issue_file(self) -> None:
        task = load_issue(str(_ISSUE_PATH))
        assert "issue_file" in task.metadata
        assert task.metadata["issue_file"] == str(_ISSUE_PATH.resolve())

    def test_constraints_default_empty(self, tmp_path: Path) -> None:
        issue = tmp_path / "issue.yaml"
        issue.write_text(
            "id: T-1\ntitle: Test\ndescription: desc\n"
            "acceptance_criteria:\n  - crit\n",
            encoding="utf-8",
        )
        task = load_issue(str(issue))
        assert task.constraints == []

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_issue("/nonexistent/issue.yaml")

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="expected mapping"):
            load_issue(str(bad))

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        issue = tmp_path / "issue.yaml"
        issue.write_text("id: T-1\ntitle: Test\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing required fields"):
            load_issue(str(issue))
