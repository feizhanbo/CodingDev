"""Offline adapter contracts; no network or provider credentials."""

import asyncio

import pytest
from langchain_core.messages import AIMessage

from devpilot.llm.base import ContextBudgetExceeded, LLMMessage
from devpilot.llm.config import LLMConfig
from devpilot.llm.langchain import LangChainLLMClient
from devpilot.llm.protocol import prepare_messages


class RecordedModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def bind(self, **kwargs):
        assert kwargs == {"response_format": {"type": "json_object"}}
        return self

    async def ainvoke(self, messages, config):
        self.calls.append(messages)
        assert len(config["callbacks"]) == 1
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


@pytest.mark.parametrize("usage", [None, {
    "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
}])
async def test_decision_and_usage_preserve_contract(usage):
    model = RecordedModel(AIMessage(
        content='{"finish":{"summary":"done","risk":"low"}}',
        usage_metadata=usage, response_metadata={"model_name": "provider-model"},
    ))
    config = LLMConfig(_env_file=None)
    client = LangChainLLMClient(config, model=model)
    messages = [LLMMessage(role="system", content="Task")]
    tools = [{"name": "repo.read_file"}]
    response = await client.chat(messages, tools)
    assert response.decision.finish.summary == "done"
    assert response.model == "provider-model"
    assert response.tokens_used == (15 if usage else None)
    assert client.last_request.status == "success"
    assert model.calls == [prepare_messages(messages, tools, config)]


async def test_parse_error_preserves_billed_usage():
    model = RecordedModel(AIMessage(content="{}", usage_metadata={
        "input_tokens": 2, "output_tokens": 1, "total_tokens": 3,
    }))
    client = LangChainLLMClient(LLMConfig(_env_file=None), model=model)
    with pytest.raises(ValueError):
        await client.chat([])
    assert client.last_request.status == "parse_error"
    assert client.last_request.total_tokens == 3
    assert len(model.calls) == 1


@pytest.mark.parametrize("error", [RuntimeError("transport"), asyncio.CancelledError()])
async def test_failure_does_not_retry(error):
    model = RecordedModel(error)
    client = LangChainLLMClient(LLMConfig(_env_file=None), model=model)
    with pytest.raises(type(error)):
        await client.chat([])
    assert len(model.calls) == 1
    assert client.last_request.total_tokens is None
    assert client.last_request.error_type == type(error).__name__


async def test_context_limit_prevents_dispatch():
    model = RecordedModel(None)
    client = LangChainLLMClient(LLMConfig(_env_file=None, max_context_chars=1), model=model)
    with pytest.raises(ContextBudgetExceeded):
        await client.chat([LLMMessage(role="system", content="Task")])
    assert model.calls == []
    assert client.last_request is None
