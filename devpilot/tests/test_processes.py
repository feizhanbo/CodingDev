"""Only spawn and terminate processes created by these temporary test cases."""

import asyncio
import os
import sys
import time

import pytest

from devpilot.processes import run_process, run_process_async
from devpilot.security import process_environment
from devpilot.storage import RunLock


def test_output_limit_is_error_and_keeps_partial_log(tmp_path):
    log = tmp_path / "log.txt"
    result = run_process(
        [sys.executable, "-c", "print('x' * 1000000)"],
        cwd=tmp_path,
        env=process_environment(),
        log=log,
        timeout=10,
        output_limit=1000,
    )
    assert result.output_limited
    assert log.stat().st_size < 1100
    assert "output limit exceeded" in log.read_text()


def test_redaction_spans_stream_chunks(tmp_path):
    key = "synthetic-private-key"
    script = (
        "import sys,time;sys.stdout.write('synthetic-');sys.stdout.flush();"
        "time.sleep(.1);sys.stdout.write('private-key');sys.stdout.flush()"
    )
    log = tmp_path / "log.txt"
    result = run_process(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=process_environment(),
        log=log,
        timeout=10,
        secrets=(key,),
    )
    assert result.exit_code == 0
    assert key not in log.read_text()
    assert "[REDACTED]" in log.read_text()


@pytest.mark.parametrize("parent_exits", [True, False])
def test_children_stop_on_parent_exit_or_timeout(tmp_path, parent_exits):
    heartbeat = tmp_path / "heartbeat"
    child = (
        "import time;from pathlib import Path;p=Path('heartbeat');"
        "\nwhile True:\n p.write_text(str(time.time()));time.sleep(.02)\n"
    )
    script = (
        "import subprocess,sys,time;from pathlib import Path;"
        f"subprocess.Popen([sys.executable,'-c',{child!r}]);"
        "\nwhile not Path('heartbeat').exists(): time.sleep(.01)\n"
        + ("" if parent_exits else "time.sleep(30)\n")
    )
    result = run_process(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=process_environment(),
        log=tmp_path / "parent.log",
        timeout=2,
    )
    assert heartbeat.exists()
    assert result.timed_out is (not parent_exits)
    first = heartbeat.read_text()
    time.sleep(0.2)
    assert heartbeat.read_text() == first


async def test_cancellation_waits_for_owned_process_cleanup(tmp_path):
    started = tmp_path / "started"
    task = asyncio.create_task(
        run_process_async(
            [
                sys.executable,
                "-c",
                "from pathlib import Path;import time;"
                "Path('started').write_text('1');time.sleep(30)",
            ],
            cwd=tmp_path,
            env=process_environment(),
            log=tmp_path / "cancel.log",
            timeout=30,
        )
    )
    deadline = time.monotonic() + 5
    while not started.exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    assert started.exists()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 5)


def test_invalid_utf8_cannot_expand_past_log_bound(tmp_path):
    log = tmp_path / "bytes.log"
    result = run_process(
        [sys.executable, "-c", "import os;os.write(1,b'\\xff'*5000)"],
        cwd=tmp_path,
        env=process_environment(),
        log=log,
        timeout=5,
        output_limit=1000,
    )
    assert result.output_limited
    assert log.stat().st_size < 1100


def test_crashed_process_releases_os_run_lock(tmp_path):
    from pathlib import Path

    package = Path(__file__).resolve().parents[1]
    script = (
        f"import sys,os;sys.path.insert(0,{str(package)!r});"
        "from devpilot.storage import RunLock;from pathlib import Path;"
        "lock=RunLock(Path('run.lock'));lock.__enter__();os._exit(0)"
    )
    result = run_process(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=process_environment(),
        log=tmp_path / "crash.log",
        timeout=5,
    )
    assert result.exit_code == 0
    with RunLock(tmp_path / "run.lock"):
        pass


@pytest.mark.skipif(os.name != "nt", reason="Windows job assignment lifecycle only")
def test_job_assignment_failure_cannot_start_candidate(tmp_path, monkeypatch):
    def unavailable(pid):
        raise OSError("synthetic job assignment failure")

    monkeypatch.setattr("devpilot.processes.WindowsJob", unavailable)
    with pytest.raises(OSError, match="synthetic"):
        run_process(
            [sys.executable, "-c", "from pathlib import Path;Path('unsafe').touch()"],
            cwd=tmp_path,
            env=process_environment(),
            log=tmp_path / "fail.log",
            timeout=5,
        )
    assert not (tmp_path / "unsafe").exists()
