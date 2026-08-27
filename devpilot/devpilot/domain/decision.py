"""Decision domain model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from devpilot.domain.plan import ImplementationPlan


class ToolAction(BaseModel):
    """A tool invocation requested by the agent."""

    tool: str
    arguments: dict[str, Any]


class FinishIntent(BaseModel):
    """The agent's intent to finish the run."""

    summary: str
    risk: Literal['low', 'medium', 'high']


class AgentDecision(BaseModel):
    """A decision made by the agent: call a tool, finish, or update the plan."""

    action: ToolAction | None = None
    finish: FinishIntent | None = None
    plan_update: ImplementationPlan | None = None
