"""Crash windows must never turn uncertain tool effects into automatic replay."""

import pytest

from devpilot.runtime.langgraph.operations import ManualRecoveryRequired, OperationJournal
from devpilot.workspace.sandbox import SandboxWorkspace


@pytest.fixture
def journal(tmp_path):
    sandbox = SandboxWorkspace(str(tmp_path), str(tmp_path / "work"), str(tmp_path / "runs"))
    return OperationJournal(sandbox, "run")


def test_completed_receipt_survives_reopen_and_reuses_result(journal):
    assert journal.begin("tool-1", {"path": "code.py"}, "before") is None
    journal.complete("tool-1", "after", {"result": "applied", "duration": 12})
    reopened = OperationJournal(journal.sandbox, "run")
    assert reopened.begin("tool-1", {"path": "code.py"}, "after") == {
        "result": "applied", "duration": 12,
    }


def test_prepared_without_result_never_replays_even_when_workspace_unchanged(journal):
    journal.begin("tool-1", {}, "before")
    with pytest.raises(ManualRecoveryRequired, match="uncertain"):
        OperationJournal(journal.sandbox, "run").begin("tool-1", {}, "before")


def test_completed_receipt_refuses_changed_arguments_or_workspace(journal):
    journal.begin("tool-1", {}, "before")
    journal.complete("tool-1", "after", {})
    with pytest.raises(ManualRecoveryRequired, match="parameters"):
        journal.begin("tool-1", {"changed": True}, "after")
    with pytest.raises(ManualRecoveryRequired, match="uncertain"):
        journal.begin("tool-1", {}, "external-edit")


def test_redacted_receipt_cannot_silently_change_replayed_result(journal):
    journal.sandbox.secrets = ("private-token-123",)
    journal.begin("tool-1", {}, "before")
    journal.complete("tool-1", "after", {"text": "private-token-123"})
    with pytest.raises(ManualRecoveryRequired, match="redacted"):
        journal.begin("tool-1", {}, "after")


def test_failed_result_write_leaves_uncertain_receipt(journal, monkeypatch):
    journal.begin("tool-1", {}, "before")

    def disk_full(*args):
        raise OSError("disk full")

    monkeypatch.setattr(journal.sandbox, "save_artifact", disk_full)
    with pytest.raises(OSError, match="disk full"):
        journal.complete("tool-1", "after", {"ok": True})
    with pytest.raises(ManualRecoveryRequired, match="uncertain"):
        journal.begin("tool-1", {}, "after")
