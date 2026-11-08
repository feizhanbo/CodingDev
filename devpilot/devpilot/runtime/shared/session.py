"""Ephemeral per-run state; never serialize clients, locks, or process handles."""

from dataclasses import dataclass, field

from devpilot.runtime.budget import RunBudget
from devpilot.tracing import MetricsCollector


@dataclass
class RunSession:
    budget: RunBudget
    metrics: MetricsCollector = field(default_factory=MetricsCollector)
    request_count: int = 0
    attempts_in_turn: int = 0
    preparation_ms: int = 0
    identity: str = ""
    validation: dict = field(default_factory=dict)
    caches: dict = field(default_factory=dict)
    services: dict = field(default_factory=dict)
