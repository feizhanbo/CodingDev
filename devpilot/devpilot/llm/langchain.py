"""LangChain transport preserving DevPilot's single JSON decision protocol."""

import asyncio
import time
import uuid

from langchain_core.callbacks import AsyncCallbackHandler

from devpilot.llm.base import LLMClient, LLMRequestRecord, LLMResponse
from devpilot.llm.decision_parser import parse_decision
from devpilot.llm.protocol import SCHEMA_HINT, prepare_messages


class _RequestEvents(AsyncCallbackHandler):
    """Retain cancellation even if framework error aggregation masks it."""

    run_inline = True

    def __init__(self):
        self.cancelled = False

    async def on_llm_error(self, error, **kwargs):
        self.cancelled = isinstance(error, asyncio.CancelledError)


class LangChainLLMClient(LLMClient):
    _SCHEMA_HINT = SCHEMA_HINT

    def __init__(self, config, *, model=None):
        self._config = config
        if model is None:
            from langchain_openai import ChatOpenAI

            model = ChatOpenAI(
                model=config.model, api_key=config.api_key,
                base_url=config.base_url,
                # Preserve the existing Chat Completions wire contract. ChatOpenAI
                # otherwise renames max_tokens to max_completion_tokens.
                extra_body={"max_tokens": config.max_tokens},
                temperature=config.temperature, max_retries=0,
                use_responses_api=False, streaming=False,
            )
        self._model = model.bind(response_format={"type": "json_object"})

    async def chat(self, messages, tools=None):
        from langsmith import tracing_context

        self.last_request = None
        prepared = prepare_messages(messages, tools, self._config)
        started = time.monotonic()
        record = LLMRequestRecord(request_id=uuid.uuid4().hex, model=self._config.model)
        self.last_request = record
        events = _RequestEvents()
        try:
            # Tracing remains local even if the shell enables LangSmith globally.
            with tracing_context(enabled=False):
                response = await self._model.ainvoke(prepared, config={"callbacks": [events]})
            record.model = response.response_metadata.get("model_name") or self._config.model
            usage = response.usage_metadata
            if usage is not None:
                record.input_tokens = usage.get("input_tokens")
                record.output_tokens = usage.get("output_tokens")
                record.total_tokens = usage.get("total_tokens")
            record.status = "parse_error"
            raw = response.content
            if not isinstance(raw, str):
                raise ValueError("Expected a JSON text response")
            decision = parse_decision(raw or "{}")
            record.status = "success"
            return LLMResponse(
                decision=decision, model=record.model, tokens_used=record.total_tokens,
                latency_ms=int((time.monotonic() - started) * 1000), raw_response=raw,
            )
        except BaseException as exc:
            if events.cancelled and not isinstance(exc, asyncio.CancelledError):
                record.error_type = "CancelledError"
                raise asyncio.CancelledError() from exc
            record.error_type = type(exc).__name__
            raise
        finally:
            record.latency_ms = int((time.monotonic() - started) * 1000)
