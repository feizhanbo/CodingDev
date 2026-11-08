"""Actual ChatOpenAI/OpenAI SDK requests over an in-memory HTTP transport."""

import asyncio
import json

import httpx
import langchain_openai
import pytest
from openai import APIStatusError, APITimeoutError
from openai.resources.chat.completions import AsyncCompletions, Completions

from devpilot.llm.base import LLMMessage
from devpilot.llm.config import LLMConfig
from devpilot.llm.langchain import LangChainLLMClient
from devpilot.llm.protocol import prepare_messages

_ASYNC_CREATE = AsyncCompletions.create
_SYNC_CREATE = Completions.create


@pytest.fixture
async def transport_client(monkeypatch, forbid_paid_model_requests):
    requests = []
    response = {"status": 200, "content": '{"finish":{"summary":"done","risk":"low"}}',
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}}

    def handler(request):
        requests.append(request)
        if "error" in response:
            raise response["error"]
        if response["status"] != 200:
            return httpx.Response(response["status"], json={"error": {"message": "fixture error"}})
        body = {"id": "chatcmpl-fixture", "object": "chat.completion", "created": 1,
                "model": "fixture-model", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": response["content"]}}]}
        if response["usage"] is not None:
            body["usage"] = response["usage"]
        return httpx.Response(200, json=body)

    model_class = langchain_openai.ChatOpenAI
    async def async_handler(request):
        if "started" in response:
            requests.append(request)
            response["started"].set()
            await response["release"].wait()
            requests.pop()
        return handler(request)

    monkeypatch.setattr(AsyncCompletions, "create", _ASYNC_CREATE)
    monkeypatch.setattr(Completions, "create", _SYNC_CREATE)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    async with httpx.AsyncClient(transport=httpx.MockTransport(async_handler)) as async_client:
        with httpx.Client(transport=httpx.MockTransport(handler)) as sync_client:
            monkeypatch.setattr(langchain_openai, "ChatOpenAI", lambda **kwargs: model_class(
                **kwargs, http_async_client=async_client, http_client=sync_client,
            ))
            client = LangChainLLMClient(LLMConfig(
                _env_file=None, api_key="offline-fixture", base_url="https://fixture.invalid/v1",
            ))
            yield client, requests, response
    assert forbid_paid_model_requests == []


@pytest.mark.parametrize("usage", [True, False])
async def test_sdk_request_and_usage_contract(transport_client, usage):
    client, requests, response = transport_client
    if not usage:
        response["usage"] = None
    messages = [LLMMessage(role="system", content="Developer"),
                LLMMessage(role="user", content="Task")]
    tools = [{"name": "repo.read_file", "description": "Read code"}]
    result = await client.chat(messages, tools)
    assert result.decision.finish.summary == "done"
    assert result.tokens_used == (5 if usage else None)
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://fixture.invalid/v1/chat/completions"
    payload = json.loads(request.content)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["stream"] is False
    assert "tools" not in payload
    assert payload["messages"] == prepare_messages(messages, tools, client._config)
    assert payload["max_tokens"] == client._config.max_tokens
    assert "max_completion_tokens" not in payload
    assert payload["temperature"] == client._config.temperature


@pytest.mark.parametrize("status", [429, 500])
async def test_sdk_does_not_retry_http_failures(transport_client, status):
    client, requests, response = transport_client
    response["status"] = status
    with pytest.raises(APIStatusError):
        await client.chat([])
    assert len(requests) == 1
    assert client.last_request.status == "api_error"
    assert client.last_request.total_tokens is None


@pytest.mark.parametrize("error", [httpx.ReadTimeout("fixture"), asyncio.CancelledError()])
async def test_transport_timeout_or_cancellation_is_not_retried(transport_client, error):
    client, requests, response = transport_client
    response["error"] = error
    expected = (asyncio.CancelledError
                if isinstance(error, asyncio.CancelledError) else APITimeoutError)
    with pytest.raises(expected):
        await client.chat([])
    assert len(requests) == 1
    assert client.last_request.error_type is not None


async def test_sdk_parse_failure_preserves_usage(transport_client):
    client, requests, response = transport_client
    response["content"] = "{}"
    with pytest.raises(ValueError):
        await client.chat([])
    assert len(requests) == 1
    assert client.last_request.status == "parse_error"
    assert client.last_request.total_tokens == 5


async def test_caller_cancellation_preserves_cancelled_error(transport_client):
    client, requests, response = transport_client
    response["started"] = asyncio.Event()
    response["release"] = asyncio.Event()
    task = asyncio.create_task(client.chat([]))
    try:
        await asyncio.wait_for(response["started"].wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        response["release"].set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert len(requests) == 1
    assert client.last_request.error_type == "CancelledError"
    assert client.last_request.total_tokens is None
