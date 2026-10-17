"""Decision domain model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator

from devpilot.domain.plan import ImplementationPlan


class ToolAction(BaseModel):
    """A tool invocation requested by the agent."""

    tool: str
    arguments: dict[str, Any]


class FinishIntent(BaseModel):
    """The agent's intent to finish the run."""

    summary: str
    risk: Literal["low", "medium", "high"]


class AgentDecision(BaseModel):
    """A decision made by the agent: call a tool, finish, or update the plan."""

    action: ToolAction | None = None
    finish: FinishIntent | None = None
    plan_update: ImplementationPlan | None = None

    @model_validator(mode="after")
    def exactly_one_branch(self) -> AgentDecision:
        if sum(x is not None for x in (self.action, self.finish, self.plan_update)) != 1:
            raise ValueError("Exactly one of action, finish or plan_update is required")
        return self
