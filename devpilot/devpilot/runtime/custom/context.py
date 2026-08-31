"""Execution context builder for the custom runtime."""

from __future__ import annotations

import json

from devpilot.domain.state import DevPilotState, Observation
from devpilot.domain.task import DevelopmentTask
from devpilot.llm import build_system_prompt, tools_to_openai_format
from devpilot.llm.base import LLMMessage
from devpilot.runtime.base import RuntimeConfig
from devpilot.tools.registry import ToolRegistry
from devpilot.tracing import TraceWriter

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

    def __init__(
        self,
        config: RuntimeConfig,
        registry: ToolRegistry,
        trace_writer: TraceWriter | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.trace_writer = trace_writer
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
        if total_chars > self.max_context_chars or len(
            state.observations
        ) > 20:
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

        # Runtime Feedback (highest priority after plan)
        if (
            state.observations
            and state.observations[-1].name == "guardrail_feedback"
        ):
            last_feedback = state.observations[-1]
            content += "\n--- RUNTIME FEEDBACK ---\n"
            data = last_feedback.data or {}
            content += f"Reason: {data.get('reason', 'unknown')}\n"
            content += f"Count: {data.get('count', 0)}\n"
            content += f"Phase: {data.get('phase', state.phase)}\n"
            content += (
                "Required: "
                f"{data.get('required_next_behavior', 'take_concrete_action')}\n"
            )
            if data.get("message"):
                content += f"Message: {data['message']}\n"

        # CURRENT TEST FAILURE (most recent failed test.run with structured
        # failure data; supersedes the generic repair block below).
        emitted_test_failure = False
        for obs in reversed(state.observations):
            if obs.name == "test.run" and not obs.success and obs.data:
                failure = obs.data.get("test_failure")
                if failure:
                    content += self._format_test_failure_block(failure)
                    emitted_test_failure = True
                break

        # Repair requirement (when tests fail and need fixing)
        if state.repair_required and not emitted_test_failure:
            content += (
                "\n--- REPAIR REQUIREMENT ---\n"
                "The current implementation is not complete. "
                "Inspect the error and make a concrete correction "
                "before requesting finish.\n"
            )

        # Observations: recent full, older compressed
        recent = state.observations[-self.max_recent_observations:]
        older = state.observations[: -self.max_recent_observations]

        if older:
            content += (
                f"\n--- Progress Summary ({len(older)} earlier steps) ---\n"
            )
            content += self._summarize_observations(older)
            structured = self._build_progress_summary(older)
            if structured:
                content += structured

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

    def _build_progress_summary(
        self, observations: list[Observation]
    ) -> str:
        """Build a structured progress summary from older observations.

        Extracts explored files, modified files, test results, and
        previous failures so the agent has a concise overview of what
        it has already done without re-reading every observation.
        """
        explored: list[str] = []
        modified: list[str] = []
        tests_run: list[str] = []
        failures: list[str] = []

        for obs in observations:
            data = obs.data or {}
            name = obs.name

            if name in ("repo.read_file", "repo_read_file"):
                path = data.get("path", "")
                if path and path not in explored:
                    explored.append(path)

            elif name in ("repo.search_code", "repo_search_code"):
                for m in data.get("matches", []):
                    p = m.get("path", "")
                    if p and p not in explored:
                        explored.append(p)

            elif name in ("repo.list_files", "repo_list_files"):
                for e in data.get("entries", []):
                    if e.get("type") == "file":
                        p = e.get("path", "")
                        if p and p not in explored:
                            explored.append(p)

            elif name in ("code.apply_patch", "code_apply_patch"):
                for f in data.get("modified_files", []):
                    if f not in modified:
                        modified.append(f)

            elif name in ("code.create_file", "code_create_file"):
                p = data.get("path", "")
                if p and p not in modified:
                    modified.append(p)
                for f in data.get("modified_files", []):
                    if f not in modified:
                        modified.append(f)

            elif name in ("test.run", "test_run"):
                passed = data.get("passed", 0)
                failed = data.get("failed", 0)
                status = "passed" if obs.success else "failed"
                tests_run.append(
                    f"  - {name} ({status}, {passed} passed,"
                    f" {failed} failed)"
                )

            if not obs.success:
                error = obs.summary or data.get("error", "")
                if error:
                    failures.append(
                        f"  - {self._truncate(error, 150)}"
                    )

        if not (
            explored or modified or tests_run or failures
        ):
            return ""

        lines = ["Progress Summary:"]

        if explored:
            lines.append("Explored:")
            for p in explored[:15]:
                lines.append(f"  - {p}")
            if len(explored) > 15:
                lines.append(
                    f"  ... (+{len(explored) - 15} more)"
                )

        if modified:
            lines.append("Modified:")
            for f in modified:
                lines.append(f"  - {f}")

        if tests_run:
            lines.append("Tests run:")
            lines.extend(tests_run)

        if failures:
            lines.append("Previous failures:")
            for f in failures[:10]:
                lines.append(f)

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

    def _format_test_failure_block(self, failure: dict) -> str:
        """Format structured test failure data as a concise context block."""
        lines = ["\n--- CURRENT TEST FAILURE ---"]
        failed_tests = failure.get("failed_tests") or []
        if failed_tests:
            lines.append("Failed tests:")
            for name in failed_tests[:10]:
                lines.append(f"  - {name}")
        errors = failure.get("errors") or []
        for err in errors[:5]:
            etype = err.get("type", "Unknown")
            message = err.get("message", "")
            lines.append(f"Error: {etype}: {message}")
            locs = err.get("locations") or []
            if locs:
                lines.append("Relevant files:")
                for loc in locs:
                    lines.append(f"  - {loc}")
        summary = failure.get("summary", "")
        if summary:
            lines.append(f"Summary: {summary}")
        lines.append(
            "Repair requirement: The current implementation is not "
            "complete. Inspect the error and make a concrete correction "
            "before requesting finish."
        )
        return self._truncate("\n".join(lines) + "\n", 1500)

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text to max_len, adding ... if truncated."""
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _compress_context(
        self, messages: list[LLMMessage], state: DevPilotState
    ) -> list[LLMMessage]:
        """Compress context if it exceeds budget or observation count."""
        old_max = self.max_recent_observations
        self.max_recent_observations = max(8, old_max // 2)
        state_content = self._build_state_content(state)
        for i, msg in enumerate(messages):
            if msg.content.startswith("Current Phase:"):
                messages[i] = LLMMessage(role="user", content=state_content)
                break
        if self.trace_writer:
            self.trace_writer.write_event(
                state.run_id,
                state.total_steps,
                state.phase,
                "context_compacted",
                data={
                    "observation_count": len(state.observations),
                    "max_recent_observations": (
                        self.max_recent_observations
                    ),
                },
            )
        self.max_recent_observations = old_max
        return messages

    def _get_phase_instruction(self, phase: str) -> str:
        """Get phase-specific instruction for the agent."""
        return _PHASE_INSTRUCTIONS.get(phase, "")
