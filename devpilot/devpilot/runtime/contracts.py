"""Stable runtime requests/outcomes. No concrete runner internals cross this boundary."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from devpilot.domain.result import AgentRunResult
from devpilot.domain.task import DevelopmentTask


@dataclass(frozen=True)
class FrozenPolicy:
    values: tuple[tuple[str, int | float], ...]

    @classmethod
    def from_config(cls, config):
        from dataclasses import asdict

        return cls(tuple(asdict(config).items()))

    def config(self):
        from devpilot.runtime.base import RuntimeConfig

        return RuntimeConfig(**dict(self.values))


@dataclass(frozen=True)
class WorkspaceStart:
    source: str
    kind: Literal["copy", "benchmark"] = "copy"
    issue_id: str | None = None


@dataclass(frozen=True)
class RunRequest:
    task: DevelopmentTask
    purpose: Literal["ordinary", "evaluation"] = "ordinary"
    workspace_start: WorkspaceStart | None = None
    policy: FrozenPolicy | None = None


@dataclass(frozen=True)
class RunOutcome:
    result: AgentRunResult
    workspace: str
    artifacts: str
    evidence: dict = field(default_factory=dict)
    statistics: dict = field(default_factory=dict)
    budget: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    final_diff: str = ""


class RuntimePort(Protocol):
    async def execute(self, request: RunRequest) -> RunOutcome: ...
    async def resume(self, run_id: str) -> RunOutcome: ...
