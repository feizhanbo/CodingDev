"""Tests verifying that trace.jsonl can be replayed to reconstruct a run.

Loads an existing run's trace.jsonl (from a FakeLLM run) and verifies:
- All expected event types are present.
- The trace tells a complete story (run_started -> ... -> run_completed).
- State/phase transitions are recorded in order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# Event types that must appear in any complete trace.
REQUIRED_EVENTS = {
    "run_started",
    "agent_decision",
    "tool_call",
    "tool_result",
    "run_completed",
}

# Expected phase progression for a successful run.
EXPECTED_PHASE_ORDER = [
    "understanding",
    "exploring",
    "implementing",
    "verifying",
    "completed",
]

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


def _find_complete_run() -> Path | None:
    """Return the most recent run directory that has a complete trace."""
    if not RUNS_DIR.is_dir():
        return None
    candidates: list[Path] = []
    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        trace_file = run_dir / "trace.jsonl"
        if not trace_file.is_file():
            continue
        events = _load_trace(trace_file)
        types = {e["event"] for e in events}
        if "run_started" in types and "run_completed" in types:
            candidates.append(run_dir)
            break
    return candidates[0] if candidates else None


def _load_trace(trace_path: Path) -> list[dict[str, Any]]:
    """Load and parse all events from a trace.jsonl file."""
    events: list[dict[str, Any]] = []
    for line in trace_file_text(trace_path).splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def trace_file_text(trace_path: Path) -> str:
    """Read the raw trace file text."""
    return trace_path.read_text(encoding="utf-8")


# Resolve the run to use for all tests (skipped if no complete run exists).
_RUN_DIR = _find_complete_run()
pytestmark = pytest.mark.skipif(_RUN_DIR is None, reason="No complete run found")


@pytest.fixture(scope="module")
def run_dir() -> Path:
    assert _RUN_DIR is not None
    return _RUN_DIR


@pytest.fixture(scope="module")
def trace_events(run_dir: Path) -> list[dict[str, Any]]:
    return _load_trace(run_dir / "trace.jsonl")


@pytest.fixture(scope="module")
def state_data(run_dir: Path) -> dict[str, Any]:
    state_file = run_dir / "state.json"
    return json.loads(state_file.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def result_data(run_dir: Path) -> dict[str, Any]:
    result_file = run_dir / "result.json"
    return json.loads(result_file.read_text(encoding="utf-8"))


class TestTraceStructure:
    """Verify the trace file has the expected event types and fields."""

    def test_trace_has_events(self, trace_events: list[dict]) -> None:
        assert len(trace_events) > 0

    def test_all_events_have_required_fields(
        self, trace_events: list[dict]
    ) -> None:
        required_fields = {"run_id", "step", "phase", "event", "timestamp"}
        for i, ev in enumerate(trace_events):
            missing = required_fields - set(ev.keys())
            assert not missing, f"Event {i} missing fields: {missing}"

    def test_run_id_consistent(self, trace_events: list[dict]) -> None:
        run_ids = {ev["run_id"] for ev in trace_events}
        assert len(run_ids) == 1, f"Multiple run_ids in trace: {run_ids}"

    def test_required_event_types_present(
        self, trace_events: list[dict]
    ) -> None:
        present = {ev["event"] for ev in trace_events}
        missing = REQUIRED_EVENTS - present
        assert not missing, f"Missing required event types: {missing}"


class TestTraceCompleteness:
    """Verify the trace tells a complete story from start to finish."""

    def test_starts_with_run_started(
        self, trace_events: list[dict]
    ) -> None:
        assert trace_events[0]["event"] == "run_started"

    def test_ends_with_run_completed(
        self, trace_events: list[dict]
    ) -> None:
        assert trace_events[-1]["event"] == "run_completed"

    def test_run_started_before_run_completed(
        self, trace_events: list[dict]
    ) -> None:
        started_idx = next(
            i for i, e in enumerate(trace_events) if e["event"] == "run_started"
        )
        completed_idx = next(
            i
            for i, e in enumerate(trace_events)
            if e["event"] == "run_completed"
        )
        assert started_idx < completed_idx

    def test_tool_call_followed_by_result(
        self, trace_events: list[dict]
    ) -> None:
        """Every tool_call event must have a matching tool_result."""
        for i, ev in enumerate(trace_events):
            if ev["event"] == "tool_call":
                tool_name = ev.get("tool")
                # Find the next tool_result for the same tool
                found = False
                for j in range(i + 1, len(trace_events)):
                    nxt = trace_events[j]
                    if nxt["event"] == "tool_result":
                        assert nxt.get("tool") == tool_name
                        found = True
                        break
                    if nxt["event"] == "tool_call":
                        break
                assert found, f"tool_call for {tool_name} at {i} has no result"

    def test_verifier_events_present_when_completed(
        self, trace_events: list[dict]
    ) -> None:
        """A completed run should have verifier_started and verifier_result."""
        present = {ev["event"] for ev in trace_events}
        assert "verifier_started" in present
        assert "verifier_result" in present
        # verifier_started must come before verifier_result
        vs_idx = next(
            i for i, e in enumerate(trace_events)
            if e["event"] == "verifier_started"
        )
        vr_idx = next(
            i for i, e in enumerate(trace_events)
            if e["event"] == "verifier_result"
        )
        assert vs_idx < vr_idx


class TestPhaseTransitions:
    """Verify state/phase transitions are recorded in the trace."""

    def test_phases_progress_in_order(
        self, trace_events: list[dict]
    ) -> None:
        """Phases should follow the valid progression (no backwards jumps).

        Not all phases must appear -- a short run may skip some -- but the
        ones that do appear must respect the canonical ordering:
        understanding -> exploring -> implementing -> verifying -> completed
        """
        phases: list[str] = []
        for ev in trace_events:
            phase = ev["phase"]
            if not phases or phases[-1] != phase:
                phases.append(phase)

        # Map each phase to its position in the canonical order.
        phase_rank = {name: i for i, name in enumerate(EXPECTED_PHASE_ORDER)}
        last_rank = -1
        for phase in phases:
            rank = phase_rank[phase]
            assert rank >= last_rank, (
                f"Phase '{phase}' (rank {rank}) appeared after "
                f"a later phase (rank {last_rank}) -- backwards transition"
            )
            last_rank = rank

    def test_final_phase_is_completed(
        self, trace_events: list[dict]
    ) -> None:
        assert trace_events[-1]["phase"] == "completed"

    def test_steps_are_monotonically_non_decreasing(
        self, trace_events: list[dict]
    ) -> None:
        steps = [ev["step"] for ev in trace_events]
        for i in range(1, len(steps)):
            assert steps[i] >= steps[i - 1], (
                f"Step decreased at event {i}: {steps[i - 1]} -> {steps[i]}"
            )


class TestTraceStateConsistency:
    """Verify the trace is consistent with state.json and result.json."""

    def test_trace_run_id_matches_state(
        self, trace_events: list[dict], state_data: dict
    ) -> None:
        assert trace_events[0]["run_id"] == state_data["run_id"]

    def test_trace_run_id_matches_result(
        self, trace_events: list[dict], result_data: dict
    ) -> None:
        assert trace_events[0]["run_id"] == result_data["run_id"]

    def test_result_status_is_completed(
        self, result_data: dict
    ) -> None:
        assert result_data["status"] == "completed"

    def test_state_phase_is_completed(
        self, state_data: dict
    ) -> None:
        assert state_data["phase"] == "completed"

    def test_modified_files_in_state(
        self, state_data: dict
    ) -> None:
        """State should record modified files."""
        files = state_data.get("modified_files", [])
        assert len(files) > 0

    def test_verifier_passed_in_trace(
        self, trace_events: list[dict]
    ) -> None:
        """The verifier_result event should report success."""
        vr = next(
            ev for ev in trace_events if ev["event"] == "verifier_result"
        )
        assert vr["data"]["success"] is True

    def test_verifier_checks_in_result(
        self, trace_events: list[dict], result_data: dict
    ) -> None:
        """Verifier checks in trace should be consistent with state."""
        vr = next(
            ev for ev in trace_events if ev["event"] == "verifier_result"
        )
        checks = vr["data"]["checks"]
        # All checks should pass for a completed run
        for check in checks:
            assert check["passed"] is True, (
                f"Verifier check '{check['name']}' failed"
            )
        # Verify key check names are present
        check_names = {c["name"] for c in checks}
        assert "visible_tests" in check_names
        assert "diff_non_empty" in check_names
