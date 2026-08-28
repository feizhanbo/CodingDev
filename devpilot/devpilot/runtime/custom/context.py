"""Execution context builder for the custom runtime."""

from __future__ import annotations

import json

from devpilot.domain.state import DevPilotState, Observation
from devpilot.domain.task import DevelopmentTask
from devpilot.llm import build_system_prompt, tools_to_openai_format
from devpilot.llm.base import LLMMessage
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.registry import ToolRegistry

_PHASE_INSTRUCTIONS: dict[str, str] = {
    "understanding": (
        "Analyze the task. Identify key goals, acceptance criteria, and "
        "constraints. Start by listing files in the repository root to "
        "understand the project structure."
    ),
    "exploring": (
        "Explore the codebase using repo tools. Use repo.search_code to "
        "find relevant code, then repo.read_file to understand the "
        "implementation. Focus on files related to the task.\n"
        "IMPORTANT: After you have read the relevant files and understand "
        "the code, provide a plan_update with your implementation plan. "
        "Do NOT keep reading the same file repeatedly - move forward to "
        "planning once you understand the code."
    ),
    "planning": (
        "Create an implementation plan with specific steps. Each step should "
        "map to acceptance criteria. Include verification approach.\n"
        "Provide a plan_update in your response, then start implementing "
        "by calling code.apply_patch or code.create_file."
    ),
    "implementing": (
        "Implement the changes. You have already read the files. Now use "
        "code.apply_patch to modify files or code.create_file to create "
        "new files. After making changes, call test.run to verify.\n"
        "Do NOT read files you have already read - proceed with "
        "implementation."
    ),
    "verifying": (
        "Review test results. If tests fail, read the error message and "
        "fix the issue with code.apply_patch. If tests pass, request "
        "finish with a summary of what you changed."
    ),
    "completed": "Task completed.",
    "failed": "Task failed.",
}


class ContextBuilder:
    """Builds the LLM message context from current agent state."""

    def __init__(self, config: RuntimeConfig, registry: ToolRegistry) -> None:
        self.config = config
        self.registry = registry
        self.max_recent_observations = 10
        self.max_context_chars = 30000

    def build(
        self, state: DevPilotState, workspace_path: str
    ) -> list[LLMMessage]:
        """Build context messages for LLM based on current state."""
        messages: list[LLMMessage] = []

        # 1. System message (always full)
        system_prompt = build_system_prompt(self.config)
        messages.append(LLMMessage(role="system", content=system_prompt))

        # 2. Tool schemas message
        tool_schemas = tools_to_openai_format(self.registry)
        if tool_schemas:
            tools_desc = "Available tools:\n" + json.dumps(
                tool_schemas, indent=2
            )
            messages.append(LLMMessage(role="system", content=tools_desc))

        # 3. Task message (always complete - never compress)
        task_content = self._build_task_content(state.task)
        messages.append(LLMMessage(role="user", content=task_content))

        # 4. State message with compressed observations
        state_content = self._build_state_content(state)
        messages.append(LLMMessage(role="user", content=state_content))

        # 5. Phase-specific instruction
        phase_instruction = self._get_phase_instruction(state.phase)
        if phase_instruction:
            messages.append(
                LLMMessage(role="user", content=phase_instruction)
            )

        # 6. Check context size and compress if needed
        total_chars = sum(len(m.content) for m in messages)
        if total_chars > self.max_context_chars:
            messages = self._compress_context(messages, state)

        return messages

    def _build_task_content(self, task: DevelopmentTask) -> str:
        """Build the task message content (always complete)."""
        criteria = "\n".join(f"- {c}" for c in task.acceptance_criteria)
        constraints = "\n".join(f"- {c}" for c in task.constraints)
        return (
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Acceptance Criteria:\n{criteria}\n"
            f"Constraints:\n{constraints}\n"
        )

    def _build_state_content(self, state: DevPilotState) -> str:
        """Build state content with observation compression."""
        content = f"Current Phase: {state.phase}\n"
        content += f"Step: {state.total_steps}/{self.config.max_steps}\n"

        # Plan (always show latest, full)
        if state.plan:
            content += (
                f"\nImplementation Plan (revision {state.plan.revision}):\n"
            )
            for step in state.plan.steps:
                content += (
                    f"  {step.id}. [{step.status}] {step.description}\n"
                )
                if step.verification_hint:
                    content += (
                        f"      Verification: {step.verification_hint}\n"
                    )

        # Observations: recent full, older compressed
        recent = state.observations[-self.max_recent_observations:]
        older = state.observations[: -self.max_recent_observations]

        if older:
            content += (
                f"\n--- Progress Summary ({len(older)} earlier steps) ---\n"
            )
            content += self._summarize_observations(older)

        if recent:
            content += (
                f"\n--- Recent Observations (last {len(recent)}) ---\n"
            )
            for obs in recent:
                status = "OK" if obs.success else "FAIL"
                content += (
                    f"  Step {obs.step_id}: [{obs.name}] {status}"
                    f" - {self._truncate(obs.summary, 200)}\n"
                )
                # Include tool result data so the LLM can see what happened
                if obs.data:
                    data_str = self._format_observation_data(obs)
                    if data_str:
                        content += f"    Result: {data_str}\n"

        if state.modified_files:
            content += (
                f"\nModified files: {', '.join(state.modified_files)}\n"
            )

        if state.retry_count > 0:
            content += (
                f"\nRepair attempts: "
                f"{state.retry_count}/{self.config.max_test_retries}\n"
            )

        return content

    def _summarize_observations(
        self, observations: list[Observation]
    ) -> str:
        """Compress older observations into a brief summary."""
        lines = []
        for obs in observations:
            status = "+" if obs.success else "-"
            summary = self._truncate(obs.summary, 100)
            lines.append(
                f"  {status} Step {obs.step_id}: {obs.name} - {summary}"
            )
        return "\n".join(lines) + "\n"

    def _format_observation_data(self, obs: Observation) -> str:
        """Format observation data for inclusion in context.

        Returns a concise string representation of the tool result data,
        truncated to avoid context bloat.
        """
        if not obs.data:
            return ""

        data = obs.data
        name = obs.name
        max_len = 800  # Max chars for tool data in context

        # Format based on tool type
        if name == "repo.list_files":
            entries = data.get("entries", [])
            paths = [e["path"] for e in entries[:30]]
            result = f"[{len(entries)} files: {', '.join(paths)}]"
            if data.get("truncated"):
                result += " (truncated)"
            return self._truncate(result, max_len)

        if name == "repo.search_code":
            matches = data.get("matches", [])
            lines = []
            for m in matches[:15]:
                lines.append(f"{m.get('path','')}:{m.get('line','')} - {m.get('text','')[:80]}")
            result = f"[{len(matches)} matches]\n" + "\n".join(lines)
            return self._truncate(result, max_len)

        if name == "repo.read_file":
            content_text = data.get("content", "")
            path = data.get("path", "")
            start = data.get("start_line", 1)
            return self._truncate(
                f"[{path} lines {start}-{data.get('end_line','?')}]\n{content_text}",
                2000,
            )

        if name == "code.apply_patch":
            files = data.get("modified_files", [])
            if files:
                return f"[modified: {', '.join(files)}]"
            return f"[{data.get('error', 'unknown')}]"

        if name == "code.create_file":
            if data.get("success"):
                return f"[created: {data.get('path', '')}]"
            return f"[failed: {data.get('error', '')}]"

        if name == "test.run":
            passed = data.get("passed", 0)
            failed = data.get("failed", 0)
            summary = data.get("summary", "")
            exit_code = data.get("exit_code", -1)
            result = f"[exit={exit_code}, {passed} passed, {failed} failed]\n{summary}"
            return self._truncate(result, max_len)

        if name == "git.diff":
            return self._truncate(data.get("diff", ""), max_len)

        if name == "git.status":
            return f"[{data.get('modified_count', 0)} files modified]\n{data.get('status', '')}"

        if name == "verification":
            checks = data.get("checks", [])
            lines = []
            for c in checks:
                mark = "PASS" if c.get("passed") else "FAIL"
                lines.append(f"  {mark}: {c.get('name', '')} - {c.get('detail', '')}")
            return "\n".join(lines) if lines else ""

        # Generic fallback: JSON dump truncated
        return self._truncate(json.dumps(data, ensure_ascii=False, default=str), max_len)

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text to max_len, adding ... if truncated."""
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _compress_context(
        self, messages: list[LLMMessage], state: DevPilotState
    ) -> list[LLMMessage]:
        """Compress context if it exceeds budget."""
        old_max = self.max_recent_observations
        self.max_recent_observations = max(3, old_max // 2)
        state_content = self._build_state_content(state)
        for i, msg in enumerate(messages):
            if msg.content.startswith("Current Phase:"):
                messages[i] = LLMMessage(role="user", content=state_content)
                break
        self.max_recent_observations = old_max
        return messages

    def _get_phase_instruction(self, phase: str) -> str:
        """Get phase-specific instruction for the agent."""
        return _PHASE_INSTRUCTIONS.get(phase, "")
