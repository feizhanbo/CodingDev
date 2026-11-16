"""Offline, deterministic business contract; excludes incidental IDs and timings."""

import json

import pytest

from devpilot.cli import initialize_components
from devpilot.domain.task import DevelopmentTask
from devpilot.settings import Settings


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
    assert result.status == "completed", result.error
    assert [o.name for o in result.observations] == [
        "repo.search_code", "repo.read_file", "code.apply_patch", "test.run",
        "code.apply_patch", "code.create_file", "test.run",
    ]
    assert result.total_steps == 7
    assert result.budget["llm_requests"] == 8
    directory = tmp_path / "runs" / result.run_id
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["retry_count"] == 1
    diff = (directory / "final.diff").read_text(encoding="utf-8")
    assert "+    return a + b" in diff
    assert "test_addition_edges.py" in diff
    assert set(result.modified_files) == {"calculator.py", "tests/test_addition_edges.py"}
