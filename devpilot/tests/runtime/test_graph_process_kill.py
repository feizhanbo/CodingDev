"""The kernel must release locks and recovery must respect durable receipts."""

import asyncio
import json
import sys

import pytest

from devpilot.storage import RunLock
from tests.runtime.test_runner import _setup_baseline


async def worker(root, mode, point, *args):
    return await asyncio.create_subprocess_exec(
        sys.executable, "-m", "tests.runtime.graph_kill_worker", str(root), mode, point, *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )


async def cleanup(process):
    if process.returncode is None:
        process.kill()
    await process.communicate()


@pytest.mark.parametrize("point", [
    "model_completed", "model_prepared", "tool_completed", "tool_prepared",
    "verify_completed", "verify_prepared", "terminal",
])
async def test_force_kill_then_recover(tmp_path, point):
    _setup_baseline(tmp_path / "baseline")
    process = await worker(tmp_path, "start", point)
    try:
        line = await asyncio.wait_for(process.stdout.readline(), timeout=90)
        assert line, "Worker exited before the requested crash window"
        run_id = json.loads(line)["ready"]
        lock_path = tmp_path / "runs" / run_id / ".run.lock"
        with pytest.raises(RuntimeError, match="already active"), RunLock(lock_path):
            pass
        assert process.returncode is None
        process.kill()
        await asyncio.wait_for(process.wait(), timeout=15)
    finally:
        await cleanup(process)
    with RunLock(lock_path):
        pass
    restarted = await worker(tmp_path, "resume", point, run_id)
    try:
        stdout, stderr = await asyncio.wait_for(restarted.communicate(), timeout=90)
    finally:
        await cleanup(restarted)
    assert restarted.returncode == 0, stderr.decode(errors="replace")
    report = json.loads(stdout.decode().splitlines()[-1])
    if point in {"tool_prepared", "verify_prepared"}:
        assert report["status"] in {"failed", "refused"}
        assert "uncertain" in report["error"]
        assert report["calls"] == 0
    else:
        assert report["status"] == "completed", report
        assert report["calls"] == (1 if point in {"tool_completed", "model_prepared"} else 0)
        assert report["requests"] == (1 if point in {"model_completed", "terminal"} else 2)
        if point == "model_prepared":
            assert report["unknown_requests"] >= 1
    if not point.startswith("model_") and point != "terminal":
        assert (tmp_path / "workspaces" / run_id / "repo" / "new.py").read_text() == "x=1\n"
    trace = tmp_path / "runs" / run_id / "trace.jsonl"
    identities = [json.loads(line)["event_id"] for line in trace.read_text().splitlines()]
    assert all(identities)
    assert len(identities) == len(set(identities))
