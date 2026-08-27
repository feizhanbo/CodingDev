"""Tool abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from devpilot.tools.context import ToolContext, ToolResult


class Tool(ABC):
    """Abstract base class for all DevPilot tools.

    Each concrete tool declares a ``name``, a detailed ``description``
    (which doubles as the LLM tool-selection prompt), and an
    ``input_model`` (a Pydantic model used to validate arguments).
    """

    name: str
    description: str
    input_model: type[BaseModel]

    @abstractmethod
    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        """Execute the tool with validated *args* under *ctx*."""
        ...
