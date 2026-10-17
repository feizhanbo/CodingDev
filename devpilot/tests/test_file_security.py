"""Synthetic markers verify policy before candidate file contents are read."""

import os
import shutil

import pytest

from devpilot.security import process_environment
from devpilot.tools.context import ToolContext
from devpilot.tools.path_guard import PathGuard
from devpilot.tools.repo.search_code import SearchCode, SearchCodeInput
from devpilot.verification.evidence import capture_snapshot
from devpilot.workspace.sandbox import SandboxWorkspace


@pytest.mark.parametrize("name", ["id_rsa", "nested/ID_ED25519", ".ENV", "x/.aws/credentials"])
async def test_forbidden_contents_excluded(tmp_path, monkeypatch, name):
    repo = tmp_path / "base"
    repo.mkdir()
    secret = repo / name
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("AUDIT_SECRET_MARKER")
    (repo / "safe.py").write_text("VALUE = 'a.b'\n")
    for rg in (shutil.which("rg"), None):
        monkeypatch.setattr("devpilot.tools.repo.search_code.shutil.which", lambda _, r=rg: r)
        result = await SearchCode().execute(
            SearchCodeInput(query="AUDIT_SECRET_MARKER"),
            ToolContext(workspace_root=str(repo), run_id="test"),
        )
        assert result.success and not result.data["matches"]
    with pytest.raises(PermissionError):
        PathGuard(str(repo)).validate_path(name)
    sandbox = SandboxWorkspace(str(repo), str(tmp_path / "ws"), str(tmp_path / "runs"))
    copied = sandbox.create("safe")
    assert not (__import__("pathlib").Path(copied) / name).exists()
    trusted = capture_snapshot(__import__("pathlib").Path(copied), tmp_path / "artifacts")
    assert "AUDIT_SECRET_MARKER" not in str(
        [p.read_text(encoding="utf-8") for p in trusted.rglob("*") if p.is_file()]
    )


async def test_rg_and_python_have_literal_semantics(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("a.b\naxb\n")
    args = SearchCodeInput(query="a.b", path="a.py")
    ctx = ToolContext(workspace_root=str(tmp_path), run_id="test")
    rg = await SearchCode().execute(args, ctx)
    monkeypatch.setattr("devpilot.tools.repo.search_code.shutil.which", lambda _: None)
    python = await SearchCode().execute(args, ctx)
    assert rg.data == python.data
    assert len(python.data["matches"]) == 1


def test_process_environment_excludes_credentials(monkeypatch):
    monkeypatch.setenv("DEVPILOT_API_KEY", "synthetic-api-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-cloud-key")
    monkeypatch.setenv("PYTHONPATH", "unsafe-user-hook")
    env = process_environment()
    assert "synthetic" not in str(env)
    assert "PYTHONPATH" not in env


async def test_actual_test_process_and_log_exclude_secrets(tmp_path, monkeypatch):
    from devpilot.tools.test.run_tests import RunTests, RunTestsInput

    monkeypatch.setenv("DEVPILOT_API_KEY", "synthetic-api-secret")
    (tmp_path / "test_env.py").write_text(
        "import os\ndef test_clean():\n"
        "    assert 'DEVPILOT_API_KEY' not in os.environ\n"
        "    print('synthetic-api-secret')\n",
        encoding="utf-8",
    )
    tool = RunTests(runs_root=str(tmp_path / "artifacts"))
    tool.secrets = ("synthetic-api-secret",)
    result = await tool.execute(
        RunTestsInput(), ToolContext(workspace_root=str(tmp_path), run_id="env")
    )
    assert result.success
    assert "synthetic-api-secret" not in str(result.data)


def test_workspace_rejects_symlink_before_copy(tmp_path):
    repo = tmp_path / "base"
    repo.mkdir()
    target = tmp_path / "outside"
    target.write_text("marker")
    try:
        os.symlink(target, repo / "link")
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    sandbox = SandboxWorkspace(str(repo), str(tmp_path / "ws"), str(tmp_path / "runs"))
    with pytest.raises(PermissionError, match="Linked"):
        sandbox.create("linked")
