"""Tool schema conversion to OpenAI function/tool format."""
from __future__ import annotations

from devpilot.tools.registry import ToolRegistry


def tools_to_openai_format(registry: ToolRegistry) -> list[dict]:
    """Convert a :class:`ToolRegistry` to the OpenAI ``tools`` format.

    Each entry follows::

        {"type": "function", "function": {"name", "description", "parameters"}}
    """
    result: list[dict] = []
    for schema in registry.list_schemas():
        result.append(
            {
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["input_schema"],
                },
            }
        )
    return result
