"""Checkpoints, redaction and failure diagnostics without touching user data."""

import json
from pathlib import Path

import pytest

from devpilot.runtime.base import RuntimeConfig
from devpilot.security import redact
from devpilot.storage import atomic_write
from tests.runtime.test_runner import (
    _make_runner,
    _make_task,
    _resp_action,
    _resp_finish,
    _setup_baseline,
)


async def test_checkpoint_visible_before_next_decision(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner(
        [_resp_action("git.status"), _resp_finish()], RuntimeConfig(), base, tmp_path
    )
    decide = runner.agent.decide
    steps = []

    async def inspect(messages):
        checkpoint = next((tmp_path / "runs").glob("*/state.json"))
        steps.append(json.loads(checkpoint.read_text())["total_steps"])
        return await decide(messages)

    runner.agent.decide = inspect
    result = await runner.run(_make_task())
    assert result.status == "completed"
    assert steps == [0, 1]


async def test_artifact_failure_keeps_recovery_result(tmp_path, monkeypatch):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner([_resp_finish()], RuntimeConfig(), base, tmp_path)

    def fail(*args):
        raise OSError("synthetic disk error")

    monkeypatch.setattr(runner.sandbox, "save_artifact", fail)
    monkeypatch.setattr("devpilot.runtime.custom.runner.tempfile.gettempdir", lambda: str(tmp_path))
    result = await runner.run(_make_task())
    assert result.artifact_errors
    assert Path(result.recovery_file).is_file()
    saved = json.loads(Path(result.recovery_file).read_text())
    assert saved["result"]["run_id"] == result.run_id


async def test_quota_rejects_preparation(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner([], RuntimeConfig(), base, tmp_path)
    runner.sandbox.max_bytes = 1
    result = await runner.run(_make_task())
    assert result.status == "failed"
    assert "workspace_max_bytes" in result.error
    assert result.budget["llm_requests"] == 0


def test_atomic_write_and_known_secret_redaction(tmp_path):
    target = tmp_path / "state.json"
    atomic_write(target, redact('{"error":"synthetic-secret"}', ("synthetic-secret",)))
    assert json.loads(target.read_text())["error"] == "[REDACTED]"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("run_id", ["..", ".", "../outside", "nested/../../outside"])
def test_destroy_rejects_resolved_targets_outside_workspace(tmp_path, monkeypatch, run_id):
    from devpilot.workspace.sandbox import SandboxWorkspace

    sandbox = SandboxWorkspace(str(tmp_path), str(tmp_path / "ws"), str(tmp_path / "runs"))
    calls = []
    monkeypatch.setattr("devpilot.workspace.sandbox.shutil.rmtree", lambda *a, **k: calls.append(a))
    with pytest.raises(PermissionError):
        sandbox.destroy(run_id)
    assert calls == []
