"""Bounded output and owned process-tree lifetime, not a security sandbox."""

from __future__ import annotations

import asyncio
import base64
import codecs
import ctypes
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from shutil import which as resolve_executable

from devpilot.security import redact
from devpilot.storage import ArtifactQuotaExceeded, active_capacity, check_active_capacity


class WindowsJob:
    """Kill descendants when the private, unnamed job handle closes (Windows 8+)."""

    def __init__(self, pid: int) -> None:
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", w.DWORD),
                ("min_ws", ctypes.c_size_t),
                ("max_ws", ctypes.c_size_t),
                ("active", w.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", w.DWORD),
                ("scheduling", w.DWORD),
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", ctypes.c_uint64 * 6),
                ("memory", ctypes.c_size_t * 4),
            ]

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        api.CreateJobObjectW.restype = w.HANDLE
        api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        api.SetInformationJobObject.restype = w.BOOL
        api.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        api.OpenProcess.restype = w.HANDLE
        api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        api.AssignProcessToJobObject.restype = w.BOOL
        api.CloseHandle.argtypes = [w.HANDLE]
        api.CloseHandle.restype = w.BOOL
        self.api = api
        self.handle = api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            limits = Extended()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not api.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            process = api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
            if not process:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not api.AssignProcessToJobObject(self.handle, process):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                api.CloseHandle(process)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


@dataclass
class ProcessResult:
    exit_code: int
    duration_ms: int
    timed_out: bool = False
    output_limited: bool = False
    cancelled: bool = False
    stdout: str = ""
    stderr: str = ""

    @property
    def returncode(self):
        return self.exit_code


def run_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log: Path,
    timeout: float,
    output_limit: int = 2097152,
    secrets: tuple[str, ...] = (),
    cancel: threading.Event | None = None,
    stdin: bytes | None = None,
) -> ProcessResult:
    """Own the process tree until exit; cap combined UTF-8 output on both streams."""
    if timeout <= 0 or output_limit <= 0:
        raise ValueError("Process limits must be positive")
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    limited = threading.Event()
    errors = []
    lock = threading.Lock()
    used = 0
    quota = active_capacity.get()
    output = [[], []]
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    launch = command
    payload = stdin or b""
    if os.name == "nt":
        executable = resolve_executable(command[0], path=env.get("PATH"))
        if executable is None:
            raise FileNotFoundError(f"Executable not found: {command[0]}")
        command = [executable, *command[1:]]
        # Target code cannot execute until Job assignment succeeds.
        launch = [
            sys.executable,
            "-I",
            "-c",
            "import base64,json,subprocess,sys;"
            "cmd,data=json.loads(sys.stdin.buffer.readline());"
            "sys.exit(subprocess.run(cmd,input=base64.b64decode(data)).returncode)",
        ]
        payload = (json.dumps([command, base64.b64encode(payload).decode()]) + "\n").encode()
    proc = subprocess.Popen(
        launch,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        **options,
    )
    job = None
    closed = False

    def stop_tree():
        nonlocal closed
        if closed:
            return
        closed = True
        if job is not None:
            job.close()
        elif os.name != "nt":
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
        if proc.poll() is None:
            with suppress(ProcessLookupError):
                proc.kill()

    def feed():
        try:
            proc.stdin.write(payload)
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            proc.stdin.close()

    marker = b"\n[output limit exceeded]\n"
    capacity = max(0, output_limit - len(marker))
    handle = None

    def consume(pipe, index):
        nonlocal used
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        pending = ""
        keep = max((len(secret) for secret in secrets), default=1) - 1

        def emit(value):
            nonlocal used
            data = value.encode("utf-8")
            with lock:
                available = max(0, capacity - used)
                accepted = data[:available].decode("utf-8", errors="ignore")
                encoded = accepted.encode("utf-8")
                if quota is not None:
                    quota.check(len(encoded))
                handle.write(encoded)
                handle.flush()
                output[index].append(accepted)
                used += len(encoded)
                if len(data) > available:
                    limited.set()

        try:
            while block := pipe.read1(8192):
                pending = redact(pending + decoder.decode(block), secrets)
                boundary = max(0, len(pending) - keep)
                emit(pending[:boundary])
                pending = pending[boundary:]
                if limited.is_set():
                    break
            emit(redact(pending + decoder.decode(b"", final=True), secrets))
        except BaseException as exc:
            errors.append(exc)
            limited.set()

    readers = [
        threading.Thread(target=consume, args=(pipe, index), daemon=True)
        for index, pipe in enumerate((proc.stdout, proc.stderr))
    ]
    writer = threading.Thread(target=feed, daemon=True)
    result = ProcessResult(-1, 0)
    try:
        if os.name == "nt":
            job = WindowsJob(proc.pid)
        handle = log.open("wb")
        for reader in readers:
            reader.start()
        writer.start()
        while True:
            check_active_capacity()
            result.timed_out = time.monotonic() - started >= timeout
            result.cancelled = cancel is not None and cancel.is_set()
            result.output_limited = limited.is_set()
            if (
                result.timed_out
                or result.cancelled
                or result.output_limited
                or proc.poll() is not None
            ):
                stop_tree()
                break
            time.sleep(0.01)
        proc.wait(timeout=5)
        for thread in [writer, *readers]:
            thread.join(timeout=5)
        if any(thread.is_alive() for thread in [writer, *readers]):
            raise RuntimeError("manual_recovery_required: process I/O did not stop")
        if errors and isinstance(errors[0], ArtifactQuotaExceeded):
            raise errors[0]
        if errors:
            raise OSError("Cannot persist process output") from errors[0]
        result.output_limited = limited.is_set()
        if result.output_limited:
            handle.write(marker[: max(0, output_limit - used)])
        result.exit_code = proc.returncode
        result.stdout, result.stderr = ("".join(parts) for parts in output)
        result.duration_ms = int((time.monotonic() - started) * 1000)
        return result
    finally:
        stop_tree()
        proc.wait(timeout=5)
        for thread in [writer, *readers]:
            if thread.ident:
                thread.join(timeout=5)
        if not any(thread.is_alive() for thread in [writer, *readers]):
            for pipe in (proc.stdout, proc.stderr, proc.stdin):
                pipe.close()
            if handle:
                handle.close()


def capture_process(
    command, *, cwd, stdin=None, timeout=120, output_limit=None, env=None, cancel=None, **compat
):
    """Bounded capture for Git/rg, with the same lifetime contract as pytest."""
    from devpilot.execution import current_policy, execution_scope, remaining
    from devpilot.security import process_environment

    with execution_scope(cancel=cancel or current_policy.get().cancel):
        policy = current_policy.get()
        from contextlib import nullcontext

        quota = active_capacity.get()
        scope = (
            nullcontext(quota.directory / "process-logs")
            if quota is not None
            else tempfile.TemporaryDirectory(prefix="devpilot-process-")
        )
        with scope as directory:
            import uuid

            result = run_process(
                command,
                cwd=Path(cwd),
                env=env or process_environment(),
                log=Path(directory) / f"{uuid.uuid4().hex}.log",
                stdin=stdin,
                timeout=remaining(timeout),
                output_limit=output_limit or policy.output_limit,
                cancel=policy.cancel,
            )
        if result.timed_out or result.cancelled:
            raise TimeoutError(policy.timeout_reason)
        if result.output_limited:
            raise ValueError("process_output_limit_exceeded: complete output required")
        if compat.get("check") and result.returncode:
            raise subprocess.CalledProcessError(
                result.returncode, command, result.stdout, result.stderr
            )
        return result


async def capture_process_async(command, **kwargs):
    return await run_cancellable(capture_process, command, **kwargs)


async def run_process_async(command: list[str], **kwargs) -> ProcessResult:
    return await run_cancellable(run_process, command, **kwargs)


async def run_cancellable(function, *args, **kwargs):
    """Do not abandon a worker on cancellation, including repeated cancellation."""
    cancel = threading.Event()
    worker = asyncio.create_task(asyncio.to_thread(function, *args, cancel=cancel, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel.set()
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        # Retrieve exceptions; the original cancellation remains authoritative.
        if not worker.cancelled():
            worker.exception()
        raise


async def run_sync(function, *args, **kwargs):
    """Cooperative synchronous operation; cleanup finishes before cancellation returns."""
    from devpilot.execution import check_execution, execution_scope

    def execute(*, cancel):
        with execution_scope(cancel=cancel):
            check_execution()
            result = function(*args, **kwargs)
            check_execution()
            return result

    return await run_cancellable(execute)
