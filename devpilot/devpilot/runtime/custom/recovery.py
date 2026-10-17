"""Conservative recovery of ordinary trusted-local runs; never replay an in-flight tool."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from devpilot.domain.state import DevPilotState
from devpilot.security import forbidden, linked


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=r"^run_[0-9a-f]{8}$")
    stage: Literal["ready", "llm_inflight", "tool_inflight", "verifier_inflight", "terminal"]
    state: DevPilotState
    request_count: int = Field(ge=0)
    attempts_in_turn: int = Field(ge=0, le=3)
    deadline_at: float
    remaining_seconds: float = Field(ge=0)
    started_at: float
    preparation_ms: int = Field(ge=0)
    identity: str
    runtime: dict
    guard: dict
    metrics: dict
    workspace: dict[str, str]
    trusted: dict[str, str]
    purpose: str = "ordinary"


def validate_run_id(run_id: str) -> None:
    if not re.fullmatch(r"run_[0-9a-f]{8}", run_id):
        raise ValueError("Invalid run ID")


def recovery_inventory(root: Path) -> dict[str, str]:
    """Include Git, databases and generated files to detect changes during downtime."""
    if not root.is_dir() or linked(root):
        raise ValueError("Recovery directory missing or linked")
    result = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(directory) / name
            relative = path.relative_to(root)
            if linked(path):
                raise PermissionError(f"Linked recovery path: {relative}")
            # The fresh workspace Git repository is also hashed, never sent as content.
            if relative.parts[0] != ".git" and forbidden(relative.as_posix()):
                raise PermissionError(f"Forbidden recovery path: {relative}")
        for name in names:
            path = Path(directory) / name
            result[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return result


def runtime_identity(runner) -> str:
    """Fingerprint source/runtime/provider without persisting keys, URLs or the environment."""
    package = Path(__file__).resolve().parents[2]
    sources = {
        p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in package.rglob("*.py")
        if "baseline" not in p.parts
    }
    client = runner.agent.llm_client
    config = getattr(client, "_config", None)
    provider = config.model_dump(exclude={"api_key"}) if config else {}
    tool = runner.registry.get("test.run")
    identity = {
        "sources": sources,
        "python": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
        "client": type(client).__module__ + type(client).__name__,
        "provider": provider,
        "test_python": getattr(tool, "python_executable", sys.executable),
        "runtime": asdict(runner.config),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def restore_fields(target, saved: dict) -> None:
    """Only restore the known data fields with the same types as a fresh instance."""
    current = {k: v for k, v in vars(target).items() if k != "config"}
    if current.keys() != saved.keys():
        raise ValueError("Checkpoint accounting fields changed")
    for key, value in saved.items():
        original = current[key]
        if (
            original is not None
            and type(value) is not type(original)
            and not (isinstance(original, float) and type(value) in (float, int))
        ):
            raise ValueError(f"Invalid checkpoint field: {key}")
        setattr(target, key, value)
