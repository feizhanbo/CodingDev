"""Offline, deterministic business contract; excludes incidental IDs and timings."""

import json

import pytest

from devpilot.cli import initialize_components
from devpilot.domain.task import DevelopmentTask
from devpilot.settings import Settings
from tests.contracts.runtime import assert_smoke_contract


async def test_paid_transport_is_blocked():
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key="synthetic-not-a-key")
    try:
        with pytest.raises(AssertionError, match="forbidden"):
            await client.chat.completions.create(model="unused", messages=[])
    finally:
        await client.close()


async def test_smoke_business_contract(tmp_path):
    runner = initialize_components(fake=True, settings=Settings(
        _env_file=None, workspace_root=str(tmp_path / "ws"), runs_root=str(tmp_path / "runs")
    ))
    outcome = await runner.run(DevelopmentTask(
        id="BASELINE", title="Fix addition", description="Fix the implementation",
        acceptance_criteria=["Addition is correct", "Add tests"],
    ))
    result = getattr(outcome, "result", outcome)
    directory = tmp_path / "runs" / result.run_id
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    diff = (directory / "final.diff").read_text(encoding="utf-8")
    assert_smoke_contract(result, state, diff)
