"""Execution context builder for the custom runtime."""

from __future__ import annotations

import json

from devpilot.domain.state import DevPilotState
from devpilot.llm import build_system_prompt, tools_to_openai_format
from devpilot.llm.base import LLMMessage
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.registry import ToolRegistry

_PHASE_INSTRUCTIONS: dict[str, str] = {
    "understanding": (
        "Analyze the task. Identify key goals, acceptance criteria, and "
        "constraints. When ready, explore the codebase."
    ),
    "exploring": (
        "Explore the codebase using repo tools. Find relevant files and "
        "understand the current implementation. When you have enough "
        "context, create an implementation plan."
    ),
    "planning": (
        "Create an implementation plan with specific steps. Each step should "
        "map to acceptance criteria. Include verification approach."
    ),
    "implementing": (
        "Implement the changes. Read files before editing. Make minimal "
        "changes. Apply patches using code.apply_patch."
    ),
    "verifying": (
        "Review test results. If tests fail, read the error and fix. "
        "If tests pass, you may request finish with a summary."
    ),
    "completed": "Task completed.",
    "failed": "Task failed.",
}


class ContextBuilder:
    """Builds the LLM message context from current agent state."""

    def __init__(self, config: RuntimeConfig, registry: ToolRegistry) -> None:
        self.config = config
        self.registry = registry

    def build(
        self, state: DevPilotState, workspace_path: str
    ) -> list[LLMMessage]:
        """Build context messages for LLM based on current state."""
        messages: list[LLMMessage] = []

        # 1. System message (system prompt + policy + repository instructions)
        system_prompt = build_system_prompt(self.config)
        messages.append(LLMMessage(role="system", content=system_prompt))

        # 2. Tool schemas message
        tool_schemas = tools_to_openai_format(self.registry)
        if tool_schemas:
            tools_desc = "Available tools:\n" + json.dumps(
                tool_schemas, indent=2
            )
            messages.append(LLMMessage(role="system", content=tools_desc))

        # 3. Task message (always complete)
        task = state.task
        criteria = "\n".join(f"- {c}" for c in task.acceptance_criteria)
        constraints = "\n".join(f"- {c}" for c in task.constraints)
        task_content = (
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Acceptance Criteria:\n{criteria}\n"
            f"Constraints:\n{constraints}\n"
        )
        messages.append(LLMMessage(role="user", content=task_content))

        # 4. State message (phase + plan + recent observations)
        state_content = f"Current Phase: {state.phase}\n"
        state_content += f"Step: {state.total_steps}/{self.config.max_steps}\n"

        if state.plan:
            state_content += f"\nCurrent Plan (revision {state.plan.revision}):\n"
            for step in state.plan.steps:
                state_content += (
                    f"  {step.id}. [{step.status}] {step.description}\n"
                )

        # Recent observations (last 10)
        recent = state.observations[-10:]
        if recent:
            state_content += "\nRecent Observations:\n"
            for obs in recent:
                status = "OK" if obs.success else "FAIL"
                state_content += (
                    f"  Step {obs.step_id}: [{obs.name}] "
                    f"{status} - {obs.summary}\n"
                )

        # Earlier observations as brief summary
        if len(state.observations) > 10:
            earlier = state.observations[:-10]
            state_content += (
                f"\n(Earlier: {len(earlier)} observations omitted)\n"
            )

        if state.modified_files:
            state_content += (
                f"\nModified files: {', '.join(state.modified_files)}\n"
            )

        if state.retry_count > 0:
            state_content += (
                f"\nTest repair retry: "
                f"{state.retry_count}/{self.config.max_test_retries}\n"
            )

        messages.append(LLMMessage(role="user", content=state_content))

        # 5. Phase-specific instruction
        phase_instruction = self._get_phase_instruction(state.phase)
        if phase_instruction:
            messages.append(
                LLMMessage(role="user", content=phase_instruction)
            )

        return messages

    def _get_phase_instruction(self, phase: str) -> str:
        """Get phase-specific instruction for the agent."""
        return _PHASE_INSTRUCTIONS.get(phase, "")
