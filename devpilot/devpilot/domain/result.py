"""Result domain model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from devpilot.domain.state import Observation


class AgentRunResult(BaseModel):
    """The final result of an agent run."""

    run_id: str
    task_id: str
    status: Literal["completed", "failed"]
    phase: str
    total_steps: int
    modified_files: list[str] = []
    observations: list[Observation] = []
    final_diff: str | None = None
    summary: str | None = None
    risk: str | None = None
    duration_ms: int | None = None
    error: str | None = None
    termination_reason: str | None = None
    execution_mode: str = "trusted_local"
    acceptance_coverage: list[dict] = []
    verification: dict | None = None
    capabilities: dict = {"network_isolation": False}
    budget: dict = {}
    artifact_errors: list[str] = []
    recovery_file: str | None = None
