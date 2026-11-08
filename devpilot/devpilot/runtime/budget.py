"""One wall-clock deadline and cumulative evaluation accounting per task."""

import time
from contextlib import contextmanager
from dataclasses import dataclass

from devpilot.execution import execution_scope


@dataclass
class RunBudget:
    started_at: float
    deadline_at: float
    deadline: float
    evaluation_limit: float
    evaluation_seconds: float = 0

    @classmethod
    def start(cls, config, recovery=None):
        started = recovery.started_at if recovery else time.time()
        until = recovery.deadline_at if recovery else started + config.max_run_seconds
        remaining = until - time.time()
        if recovery:
            remaining = min(remaining, recovery.remaining_seconds)
        return cls(
            started,
            until,
            time.monotonic() + remaining,
            config.evaluation_timeout_seconds,
            recovery.evaluation_seconds if recovery else 0,
        )

    def remaining(self):
        value = min(self.deadline - time.monotonic(), self.deadline_at - time.time())
        if value <= 0:
            raise TimeoutError("max_run_seconds")
        return value

    @contextmanager
    def evaluation(self):
        remaining = min(self.remaining(), self.evaluation_limit - self.evaluation_seconds)
        if remaining <= 0:
            raise TimeoutError("evaluation_timeout_seconds")
        started = time.monotonic()
        until = started + remaining
        try:
            with execution_scope(deadline=until, timeout_reason="evaluation_timeout_seconds"):
                yield until
        finally:
            self.evaluation_seconds += time.monotonic() - started

    def snapshot(self):
        return {
            "started_at": self.started_at,
            "deadline_at": self.deadline_at,
            "remaining_seconds": max(
                0, min(self.deadline - time.monotonic(), self.deadline_at - time.time())
            ),
            "evaluation_seconds": self.evaluation_seconds,
            "evaluation_remaining_seconds": max(0, self.evaluation_limit - self.evaluation_seconds),
            "budget_semantics": "whole_task_v2",
        }
