"""Tool schema conversion to OpenAI function/tool format."""
from __future__ import annotations

from devpilot.tools.registry import ToolRegistry


def tools_to_openai_format(registry: ToolRegistry) -> list[dict]:
    """Convert a :class:`ToolRegistry` to the OpenAI ``tools`` format.

    Each entry follows::

        {"type": "function", "function": {"name", "description", "parameters"}}

    Tool names with dots (e.g. ``repo.list_files``) are converted to
    underscores (``repo_list_files``) because the OpenAI API only allows
    alphanumeric characters and underscores in function names.
    """
    result: list[dict] = []
    for schema in registry.list_schemas():
        safe_name = schema["name"].replace(".", "_")
        result.append(
            {
                "type": "function",
                "function": {
                    "name": safe_name,
                    "description": schema["description"],
                    "parameters": schema["input_schema"],
                },
            }
        )
    return result
