"""Wire-compatible prompt construction shared by model transports."""

import json

from devpilot.llm.base import ContextBudgetExceeded

SCHEMA_HINT = (
    "\n\nYou MUST respond with a JSON object matching this schema:\n"
    '{"action": {"tool": "string", "arguments": {}}, "finish": '
    '{"summary": "string", "risk": "low|medium|high"}, '
    '"plan_update": {"goal": "string", "steps": [{"id": int, '
    '"description": "string", "status": "pending|running|completed'
    '|failed|skipped", "verification_hint": "string|null"}], '
    '"revision": int}}\n\n'
    "Provide exactly one of: action, finish, or plan_update.\n"
    "Use tool names with dots (e.g. repo.search_code, code.apply_patch, "
    "test.run, git.diff, git.status, repo.list_files, repo.read_file, "
    "code.create_file)."
)

def prepare_messages(messages, tools, config):
    prepared = [
        {"role": message.role, "content": message.content + (
            SCHEMA_HINT if index == 0 and message.role == "system" else ""
        )}
        for index, message in enumerate(messages)
    ]
    if tools and not any(m.content.startswith("Available tools:") for m in messages):
        prepared.append({"role": "system", "content": "Available tools:\n" +
                         json.dumps(tools, indent=2, ensure_ascii=False)})
    if sum(len(m["content"]) for m in prepared) > config.max_context_chars:
        raise ContextBudgetExceeded("context_budget_exceeded")
    return prepared
