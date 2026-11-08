"""Recovery must not combine mismatched run identities or budget origins."""

from copy import deepcopy

import pytest

from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.langgraph.recovery import checkpoint_from_graph
from devpilot.runtime.shared.state_manager import StateManager


@pytest.fixture
def snapshot():
    state = StateManager(RuntimeConfig()).create(DevelopmentTask(
        id="T", title="T", description="T", acceptance_criteria=[],
    ), "run_12345678")
    return {
        "domain": state.model_dump(),
        "accounting": {
            "request_count": 2, "attempts_in_turn": 1, "metrics": {}, "guard": {},
            "budget": {"started_at": 100.0, "deadline_at": 200.0,
                       "remaining_seconds": 40.0, "evaluation_seconds": 12.0,
                       "budget_semantics": "whole_task_v2"},
        },
        "recovery": {
            "schema_version": 1, "runtime_kind": "langgraph", "run_id": "run_12345678",
            "runtime": {}, "identity": "same", "started_at": 100.0, "deadline_at": 200.0,
            "preparation_ms": 10, "workspace": {"code.py": "hash"}, "trusted": {},
            "purpose": "ordinary",
        },
    }


def project(snapshot):
    return checkpoint_from_graph(snapshot, run_id="run_12345678", runtime={}, identity="same")


def test_projection_preserves_accounting_and_does_not_mutate_graph(snapshot):
    original = deepcopy(snapshot)
    result = project(snapshot)
    assert result.request_count == 2
    assert result.remaining_seconds == 40
    assert result.deadline_at == 200
    assert result.evaluation_seconds == 12
    assert result.workspace == {"code.py": "hash"}
    assert snapshot == original


@pytest.mark.parametrize("section,key,value", [
    ("recovery", "schema_version", 2),
    ("recovery", "runtime_kind", "custom"),
    ("recovery", "run_id", "run_87654321"),
    ("domain", "run_id", "run_87654321"),
    ("recovery", "runtime", {"max_steps": 99}),
    ("recovery", "identity", "different"),
    ("recovery", "deadline_at", 300),
    ("recovery", "started_at", 101),
])
def test_mismatched_snapshot_refused(snapshot, section, key, value):
    snapshot[section][key] = value
    with pytest.raises(ValueError):
        project(snapshot)


def test_missing_metadata_refused(snapshot):
    del snapshot["recovery"]
    with pytest.raises(KeyError):
        project(snapshot)
