"""OpenAI-compatible LLM client."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import openai

from devpilot.domain.decision import AgentDecision
from devpilot.llm.base import ContextBudgetExceeded, LLMClient, LLMMessage, LLMRequestRecord, LLMResponse
from devpilot.llm.config import LLMConfig


class OpenAIClient(LLMClient):
    """LLM client backed by the OpenAI-compatible API.

    Uses ``json_object`` response format for maximum compatibility
    (OpenAI, DeepSeek, Azure, local LLMs).  The AgentDecision schema
    is injected into the system prompt so the model knows the expected
    JSON structure.
    """

    # Schema description appended to the first system message
    _SCHEMA_HINT = (
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

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        kwargs: dict[str, Any] = {"api_key": config.api_key, "max_retries": 0}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = openai.AsyncOpenAI(**kwargs)

    async def chat(
        self, messages: list[LLMMessage], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Send a chat request and return a parsed AgentDecision."""
        # Inject schema hint into the first system message
        openai_messages: list[dict[str, Any]] = []
        for i, msg in enumerate(messages):
            content = msg.content
            if i == 0 and msg.role == "system":
                content = content + self._SCHEMA_HINT
            openai_messages.append({"role": msg.role, "content": content})

        response_format: dict[str, Any] = {"type": "json_object"}

        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": openai_messages,
            "response_format": response_format,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
        }
        # Include tool descriptions in the prompt instead of as function
        # calling parameters for maximum provider compatibility.
        if tools and not any(m.content.startswith("Available tools:") for m in messages):
            tools_desc = json.dumps(tools, indent=2, ensure_ascii=False)
            kwargs["messages"].append(
                {
                    "role": "system",
                    "content": f"Available tools:\n{tools_desc}",
                }
            )

        if sum(len(m["content"]) for m in kwargs["messages"]) > self._config.max_context_chars:
            raise ContextBudgetExceeded("context_budget_exceeded")

        start = time.monotonic()
        record = LLMRequestRecord(request_id=uuid.uuid4().hex, model=self._config.model)
        self.last_request = record
        try:
            # Runtime owns retries so every transport attempt is observable.
            completion = await self._client.chat.completions.create(**kwargs)
            record.model = completion.model
            if completion.usage is not None:
                record.input_tokens = completion.usage.prompt_tokens
                record.output_tokens = completion.usage.completion_tokens
                record.total_tokens = completion.usage.total_tokens
            record.status = "parse_error"
            raw_content = completion.choices[0].message.content or "{}"
            decision = self._parse_decision(raw_content)
            record.status = "success"
            return LLMResponse(
                decision=decision,
                model=completion.model,
                tokens_used=record.total_tokens,
                latency_ms=int((time.monotonic() - start) * 1000),
                raw_response=raw_content,
            )
        except Exception as exc:
            record.error_type = type(exc).__name__
            raise
        finally:
            record.latency_ms = int((time.monotonic() - start) * 1000)

    @staticmethod
    def _parse_decision(raw: str) -> AgentDecision:
        """Parse AgentDecision from raw LLM output.

        Handles markdown code blocks, extra text, and multi-line JSON.
        """
        import logging

        text = raw.strip()

        # Strip markdown code block wrappers
        if text.startswith("```"):
            # Remove opening ```json or ```
            lines = text.split("\n")
            # Find first line without ```
            json_lines = []
            in_block = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("```"):
                    if in_block:
                        # Closing block - stop
                        break
                    else:
                        # Opening block - skip this line
                        in_block = True
                        continue
                if in_block or not json_lines:
                    json_lines.append(line)
            if json_lines:
                text = "\n".join(json_lines).strip()

        # Try direct parse first
        try:
            return AgentDecision.model_validate_json(text)
        except Exception:
            pass

        # Try to extract the first JSON object from the text
        start = text.find("{")
        if start == -1:
            logging.error("No JSON object found in LLM response")
            raise ValueError("No JSON object found in LLM response")

        # Find matching closing brace
        depth = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        json_str = text[start:end]
        try:
            return AgentDecision.model_validate_json(json_str)
        except Exception as exc:
            logging.error("Failed to parse AgentDecision (response contents omitted)")
            raise ValueError("Failed to parse AgentDecision") from exc
