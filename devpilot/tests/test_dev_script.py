"""The Windows helper must not turn a failed native check into success."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("action", ["lint", "test", "lint:devpilot", "test:shopflow"])
def test_native_failures_propagate(action, tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell unavailable; exercised by Windows CI")
    script = Path(__file__).resolve().parents[2] / "dev.ps1"
    escaped = str(script).replace("'", "''")
    command = (
        "function global:uv { $global:LASTEXITCODE = 7 }; "
        f"& '{escaped}' '{action}'"
    )
    result = subprocess.run([shell, "-NoProfile", "-Command", command], cwd=tmp_path,
                            capture_output=True, encoding="utf-8", errors="replace")
    assert result.returncode != 0
    assert "exit code 7" in result.stderr
