"""State domain model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from devpilot.domain.plan import ImplementationPlan
from devpilot.domain.task import DevelopmentTask


class Observation(BaseModel):
    """An observation produced by a tool, runtime, or verifier."""

    step_id: int
    source: Literal['tool', 'runtime', 'verifier']
    name: str
    success: bool
    summary: str
    data: dict[str, Any] | None = None
    duration_ms: int | None = None


class TestRun(BaseModel):
    """The result of a single test execution."""

    run_id: str
    exit_code: int
    passed: int | None = None
    failed: int | None = None
    duration_ms: int
    summary: str
    log_file: str | None = None


class DevPilotState(BaseModel):
    """The full state of a DevPilot agent run."""

    run_id: str
    task: DevelopmentTask
    phase: Literal[
        'understanding', 'exploring', 'planning',
        'implementing', 'verifying', 'completed', 'failed',
    ]
    plan: ImplementationPlan | None = None
    observations: list[Observation] = []
    modified_files: list[str] = []
    test_runs: list[TestRun] = []
    current_step: int = 0
    total_steps: int = 0
    retry_count: int = 0
    completion_requested: bool = False
    repair_required: bool = False
