"""Tool registry: registration, lookup, execution dispatch, and schema export."""

from __future__ import annotations

import time
from typing import Any

from pydantic import ValidationError

from devpilot.domain.decision import ToolAction
from devpilot.tools.base import Tool
from devpilot.tools.context import ToolContext, ToolResult


class ToolRegistry:
    """In-memory registry mapping tool names to :class:`Tool` instances."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool. Raises ``ValueError`` if the name is taken."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Return the tool registered under *name*, or ``None``."""
        return self._tools.get(name)

    async def execute(self, action: ToolAction, ctx: ToolContext) -> ToolResult:
        """Validate *action*, dispatch to the target tool, handle errors.

        Returns a :class:`ToolResult` (never raises) so callers can treat
        every outcome uniformly.
        """
        tool = self.get(action.tool)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {action.tool}",
            )

        try:
            args = tool.input_model.model_validate(action.arguments)
        except ValidationError as exc:
            return ToolResult(
                success=False,
                error=f"Invalid arguments for '{action.tool}': {exc}",
            )

        start = time.monotonic()
        try:
            result = await tool.execute(args, ctx)
        except PermissionError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - registry must not raise
            return ToolResult(
                success=False,
                error=f"Tool '{action.tool}' failed: {exc}",
            )

        if result.duration_ms is None:
            result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    def list_schemas(self) -> list[dict[str, Any]]:
        """Return ``[{name, description, input_schema}]`` for each tool."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_model.model_json_schema(),
            }
            for tool in self._tools.values()
        ]

    @property
    def names(self) -> list[str]:
        """Names of all registered tools."""
        return list(self._tools)
