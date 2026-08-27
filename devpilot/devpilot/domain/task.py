"""Task domain model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DevelopmentTask(BaseModel):
    """A development task to be executed by the agent."""

    id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    constraints: list[str] = []
    metadata: dict[str, Any] = {}
