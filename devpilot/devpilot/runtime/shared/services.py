"""Replaceable decision, tool execution, and independent acceptance services."""
import asyncio
import time

from devpilot.domain.decision import AgentDecision


class DecisionService:
    async def decide(self, agent, registry, messages, timeout):
        decision = await asyncio.wait_for(agent.decide(messages), timeout)
        decision = AgentDecision.model_validate(decision.model_dump())
        if decision.action:
            decision.action.tool = registry.canonical_name(decision.action.tool)
        return decision


class ToolExecutionService:
    async def execute(self, registry, action, context, timeout):
        try:
            result = await asyncio.wait_for(registry.execute(action, context), timeout)
            if context.deadline is not None and time.monotonic() >= context.deadline:
                raise TimeoutError("tool_timeout_seconds")
            return result
        except TimeoutError as exc:
            reason = ("manual_recovery_required" if action.tool == "code.create_file"
                      else "tool_timeout_seconds")
            raise TimeoutError(reason) from exc


class AcceptanceService:
    async def verify(self, verifier, task, workspace, state, registry, budget):
        with budget.evaluation() as deadline:
            verifier.deadline = deadline
            try:
                return await asyncio.wait_for(
                    verifier.verify(task, workspace, state, registry),
                    max(0.001, deadline - time.monotonic()),
                )
            except TimeoutError as exc:
                raise TimeoutError("evaluation_timeout_seconds") from exc
