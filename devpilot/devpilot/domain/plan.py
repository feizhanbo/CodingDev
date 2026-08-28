"""Plan domain model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator


class PlanStep(BaseModel):
    """A single step in an implementation plan."""

    id: int
    description: str
    status: Literal['pending', 'running', 'completed', 'failed', 'skipped']
    verification_hint: str | None = None

    @field_validator('status', mode='before')
    @classmethod
    def normalize_status(cls, v: str) -> str:
        """Normalize common status variations from LLM output."""
        if isinstance(v, str):
            v = v.strip().lower()
            # Common LLM variations
            if v in ('in_progress', 'in-progress', 'active', 'doing'):
                return 'running'
            if v in ('done', 'finished', 'complete', 'success'):
                return 'completed'
            if v in ('error', 'fail'):
                return 'failed'
            if v in ('skip', 'skipped_step'):
                return 'skipped'
        return v


class ImplementationPlan(BaseModel):
    """An implementation plan consisting of ordered steps."""

    goal: str
    steps: list[PlanStep]
    revision: int = 1
