"""Bounded output and owned process-tree lifetime, not a security sandbox."""

from __future__ import annotations

import asyncio
import codecs
import ctypes
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from devpilot.security import redact


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
) -> ProcessResult:
    """Stream stdout to a capped log; clean up children even if the parent exits first."""
    if timeout <= 0 or output_limit <= 0:
        raise ValueError("Process limits must be positive")
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    limited = threading.Event()
    read_errors: list[BaseException] = []
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    launch = command
    if os.name == "nt":
        executable = shutil.which(command[0], path=env.get("PATH"))
        if executable is None:
            raise FileNotFoundError("Test interpreter not found")
        command = [executable, *command[1:]]
        # The trusted bootstrap waits before launching target code, closing the race
        # between CreateProcess and job assignment. No candidate executes outside the job.
        launch = [
            sys.executable,
            "-I",
            "-c",
            "import json,subprocess,sys;"
            "cmd=json.loads(sys.stdin.buffer.readline());"
            "sys.exit(subprocess.call(cmd,stdin=subprocess.DEVNULL))",
        ]
    proc = subprocess.Popen(
        launch,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE if os.name == "nt" else subprocess.DEVNULL,
        **options,
    )
    job = None
    closed = False

    def stop_tree() -> None:
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

    def consume() -> None:
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        pending = ""
        keep = max(0, max((len(s) for s in secrets), default=1) - 1)
        used = 0
        written = 0
        try:
            with log.open("w", encoding="utf-8", newline="") as handle:

                def write_bounded(text: str) -> None:
                    nonlocal written
                    encoded = text.encode("utf-8")
                    remaining = output_limit - written
                    safe = encoded[:remaining].decode("utf-8", errors="ignore")
                    handle.write(safe)
                    written += len(safe.encode("utf-8"))
                    if len(encoded) > remaining:
                        limited.set()

                while block := proc.stdout.read1(8192):
                    available = output_limit - used
                    accepted = block[:available]
                    used += len(accepted)
                    pending = redact(pending + decoder.decode(accepted), secrets)
                    end = max(0, len(pending) - keep)
                    write_bounded(pending[:end])
                    pending = pending[end:]
                    handle.flush()
                    if len(block) > available or limited.is_set():
                        limited.set()
                        break
                write_bounded(redact(pending + decoder.decode(b"", final=True), secrets))
                if limited.is_set():
                    handle.write("\n[output limit exceeded]\n")
        except BaseException as exc:
            read_errors.append(exc)
            limited.set()

    reader = threading.Thread(target=consume, daemon=True)
    result = ProcessResult(-1, 0)
    try:
        if os.name == "nt":
            job = WindowsJob(proc.pid)
            if time.monotonic() - started >= timeout or (cancel is not None and cancel.is_set()):
                stop_tree()
            else:
                proc.stdin.write((json.dumps(command) + "\n").encode("utf-8"))
            proc.stdin.close()
        reader.start()
        while True:
            result.timed_out = time.monotonic() - started >= timeout
            result.cancelled = cancel is not None and cancel.is_set()
            result.output_limited = limited.is_set()
            if result.timed_out or result.cancelled or result.output_limited:
                stop_tree()
                break
            if proc.poll() is not None:
                stop_tree()
                break
            time.sleep(0.02)
        proc.wait(timeout=5)
        reader.join(timeout=5)
        if reader.is_alive():
            raise RuntimeError("Process output reader did not stop after tree cleanup")
        if read_errors:
            raise OSError("Cannot persist process output") from read_errors[0]
        result.output_limited = limited.is_set()
        result.exit_code = proc.returncode
        result.duration_ms = int((time.monotonic() - started) * 1000)
        return result
    finally:
        stop_tree()
        proc.wait(timeout=5)
        if reader.ident:
            reader.join(timeout=5)
        # An escaped/hostile descendant can hold the pipe open outside our process group.
        # Never block forever acquiring a BufferedReader lock from its daemon reader.
        if not reader.is_alive():
            proc.stdout.close()
        if proc.stdin is not None:
            proc.stdin.close()


async def run_process_async(command: list[str], **kwargs) -> ProcessResult:
    return await run_cancellable(run_process, command, **kwargs)


async def run_cancellable(function, *args, **kwargs):
    """Wait for worker cleanup on cancellation instead of abandoning a background thread."""
    cancel = threading.Event()
    worker = asyncio.create_task(asyncio.to_thread(function, *args, cancel=cancel, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel.set()
        await asyncio.shield(worker)
        raise
