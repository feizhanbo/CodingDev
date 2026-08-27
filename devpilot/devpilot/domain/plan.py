"""Plan domain model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PlanStep(BaseModel):
    """A single step in an implementation plan."""

    id: int
    description: str
    status: Literal['pending', 'running', 'completed', 'failed', 'skipped']
    verification_hint: str | None = None


class ImplementationPlan(BaseModel):
    """An implementation plan consisting of ordered steps."""

    goal: str
    steps: list[PlanStep]
    revision: int = 1
