"""Metrics collector for agent runs."""

from __future__ import annotations

import time


class MetricsCollector:
    """Collects runtime metrics during an agent run."""

    def __init__(self) -> None:
        self.total_steps: int = 0
        self.tool_calls: int = 0
        self.tool_failures: int = 0
        self.test_retries: int = 0
        self.modified_files: list[str] = []
        self.start_time: float = 0
        self.tokens_used: int = 0
        self.finish_rejected_count: int = 0

    def record_tool_call(self, success: bool) -> None:
        """Record a tool call outcome."""
        self.tool_calls += 1
        if not success:
            self.tool_failures += 1

    def record_test_retry(self) -> None:
        """Record a test retry (failed test run)."""
        self.test_retries += 1

    def record_finish_rejected(self) -> None:
        """Record a verifier rejection of agent finish."""
        self.finish_rejected_count += 1

    def record_tokens(self, tokens: int) -> None:
        """Record token usage."""
        self.tokens_used += tokens

    def record_modified_file(self, path: str) -> None:
        """Record a modified file path."""
        if path not in self.modified_files:
            self.modified_files.append(path)

    def to_dict(self) -> dict:
        """Return metrics as a dict for ``result.json``."""
        failure_rate = (
            self.tool_failures / self.tool_calls
            if self.tool_calls > 0
            else 0.0
        )
        duration_ms = (
            int((time.time() - self.start_time) * 1000)
            if self.start_time > 0
            else 0
        )
        return {
            "total_steps": self.total_steps,
            "tool_calls": self.tool_calls,
            "tool_failure_rate": round(failure_rate, 4),
            "test_retries": self.test_retries,
            "modified_files": len(self.modified_files),
            "duration_ms": duration_ms,
            "tokens": self.tokens_used,
            "finish_rejected_count": self.finish_rejected_count,
        }
