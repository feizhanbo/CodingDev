"""Bound model attempts independently of successful tool observations."""

import asyncio
import json

import pytest

from devpilot.domain.decision import AgentDecision
from devpilot.runtime.base import RuntimeConfig
from tests.runtime.test_runner import (
    _make_runner,
    _make_task,
    _resp_action,
    _setup_baseline,
)


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {
            "action": {"tool": "git.status", "arguments": {}},
            "finish": {"summary": "done", "risk": "low"},
        },
    ],
)
def test_invalid_decision_rejected(raw):
    with pytest.raises(ValueError, match="Exactly one"):
        AgentDecision.model_validate(raw)


async def test_failed_attempts_consume_request_budget(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner([], RuntimeConfig(max_llm_requests=2), base, tmp_path)
    calls = []

    async def invalid(messages):
        calls.append(1)
        return AgentDecision.model_validate({})

    runner.agent.decide = invalid
    result = await runner.run(_make_task())
    assert len(calls) == 2
    assert result.status == "failed"
    assert result.termination_reason == "max_llm_requests"
    saved = json.loads((tmp_path / "runs" / result.run_id / "result.json").read_text())
    assert saved["budget"]["llm_requests"] == 2
    assert result.total_steps == 0


async def test_model_timeout_is_bounded(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner([], RuntimeConfig(llm_timeout_seconds=0.01), base, tmp_path)

    async def slow(messages):
        await asyncio.sleep(10)

    runner.agent.decide = slow
    result = await asyncio.wait_for(runner.run(_make_task()), 5)
    assert result.status == "failed"
    assert result.budget["llm_requests"] == 3


async def test_run_deadline_stops_further_attempts(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner([], RuntimeConfig(max_run_seconds=0.02), base, tmp_path)

    async def slow(messages):
        await asyncio.sleep(10)

    runner.agent.decide = slow
    result = await runner.run(_make_task())
    assert result.termination_reason == "max_run_seconds"
    assert result.budget["llm_requests"] == 1


async def test_alias_has_canonical_observation(tmp_path):
    base = tmp_path / "base"
    _setup_baseline(base)
    runner = _make_runner(
        [_resp_action("test_run", target="missing.py")],
        RuntimeConfig(max_test_retries=1),
        base,
        tmp_path,
    )
    result = await runner.run(_make_task())
    assert result.status == "failed"
    assert result.observations[-1].name == "test.run"
    assert "Max retries" in result.error
