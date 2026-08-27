"""Runtime base classes and configuration."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    """Configuration for the agent runtime loop.

    Controls loop budgets enforced by the Runtime (design doc §5, §13).
    """

    max_steps: int = 30
    max_test_retries: int = 3
