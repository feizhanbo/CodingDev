"""Tests for pytest output failure parsing (tasks B01-B03)."""

from __future__ import annotations

from pathlib import Path

from devpilot.domain.state import DevPilotState, Observation
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.runtime.custom.runner import CustomAgentRunner
from devpilot.runtime.custom.state_manager import StateManager
from devpilot.tools.context import ToolResult
from devpilot.tools.test.failure_parser import parse_test_failures

# Realistic pytest ``--tb=short`` output samples (all lines < 100 chars).

SAMPLE_TYPEERROR = """\
============================= test session starts ==============================
collected 1 item

tests/api/test_orders.py::test_filter F

=================================== FAILURES ===================================
_________________ test_filter _________________
tests/api/test_orders.py:12: in test_filter
    result = OrderService.list_orders(status="paid")
app/services/order_service.py:45: in list_orders
E   TypeError: unexpected keyword argument 'status'
=========================== short test summary info ============================
FAILED tests/api/test_orders.py::test_filter - TypeError: unexpected kwarg
========================= 1 failed in 0.12s =========================
"""

SAMPLE_MULTIPLE = """\
=================================== FAILURES ===================================
_________________ test_create _________________
tests/api/test_orders.py:5: in test_create
    create_order({"amount": -1})
app/services/order_service.py:20: in create_order
    raise ValueError("amount must be positive")
E   ValueError: amount must be positive
_________________ test_filter _________________
tests/api/test_orders.py:12: in test_filter
    result = OrderService.list_orders(status="paid")
app/services/order_service.py:45: in list_orders
E   TypeError: unexpected keyword argument 'status'
=========================== short test summary info ============================
FAILED tests/api/test_orders.py::test_create - ValueError: amount must be positive
FAILED tests/api/test_orders.py::test_filter - TypeError: unexpected kwarg
========================= 2 failed in 0.10s =========================
"""

SAMPLE_ASSERT = """\
_________________ test_bad_value _________________
tests/unit/test_calc.py:7: in test_bad_value
    assert compute(2) == 5
E   assert 4 == 5
=========================== short test summary info ============================
FAILED tests/unit/test_calc.py::test_bad_value - assert 4 == 5
========================= 1 failed in 0.04s =========================
"""

SAMPLE_IMPORT = """\
_________________ test_imports _________________
tests/test_imports.py:2: in test_imports
    from app.services.order_service import list_orders
E   ImportError: cannot import name 'list_orders'
=========================== short test summary info ============================
FAILED tests/test_imports.py::test_imports - ImportError: cannot import name
========================= 1 failed in 0.05s =========================
"""

SAMPLE_TIMEOUT = "Test timed out; no output captured.\n"

SAMPLE_FALLBACK = "some random garbage output\n3 failed, 7 passed in 1.2s\n"


def _make_task() -> DevelopmentTask:
    return DevelopmentTask(
        id="DEV-001",
        title="Add order endpoint",
        description="Create POST /orders",
        acceptance_criteria=["Returns 201"],
        constraints=["No schema changes"],
    )


class TestParseTestFailures:
    def test_single_typeerror_failure(self) -> None:
        result = parse_test_failures(SAMPLE_TYPEERROR)
        assert result["kind"] == "test_failure"
        assert "tests/api/test_orders.py::test_filter" in result["failed_tests"]
        errors = result["errors"]
        assert len(errors) == 1
        assert errors[0]["type"] == "TypeError"
        assert "unexpected keyword argument" in errors[0]["message"]
        locs = errors[0]["locations"]
        assert "app/services/order_service.py:45" in locs
        assert "tests/api/test_orders.py:12" in locs

    def test_multiple_failures(self) -> None:
        result = parse_test_failures(SAMPLE_MULTIPLE)
        failed = result["failed_tests"]
        assert len(failed) == 2
        assert "tests/api/test_orders.py::test_create" in failed
        assert "tests/api/test_orders.py::test_filter" in failed
        types = {e["type"] for e in result["errors"]}
        assert types == {"ValueError", "TypeError"}

    def test_assertion_error(self) -> None:
        result = parse_test_failures(SAMPLE_ASSERT)
        assert "tests/unit/test_calc.py::test_bad_value" in result["failed_tests"]
        errors = result["errors"]
        assert len(errors) == 1
        assert errors[0]["type"] == "AssertionError"
        assert errors[0]["message"] == "assert 4 == 5"
        assert "tests/unit/test_calc.py:7" in errors[0]["locations"]

    def test_import_error(self) -> None:
        result = parse_test_failures(SAMPLE_IMPORT)
        assert "tests/test_imports.py::test_imports" in result["failed_tests"]
        errors = result["errors"]
        assert len(errors) == 1
        assert errors[0]["type"] == "ImportError"
        assert "cannot import name" in errors[0]["message"]

    def test_timeout_no_output(self) -> None:
        result = parse_test_failures(SAMPLE_TIMEOUT)
        assert result["kind"] == "test_failure"
        assert result["failed_tests"] == []
        assert result["errors"] == []
        assert "timed out" in result["summary"].lower()

    def test_unparseable_output_fallback_summary(self) -> None:
        result = parse_test_failures(SAMPLE_FALLBACK)
        assert result["kind"] == "test_failure"
        assert result["failed_tests"] == []
        assert result["errors"] == []
        assert result["summary"] == "3 failed, 7 passed"

    def test_complete_log_preserved(self, tmp_path: Path) -> None:
        # Parser must not mutate its input.
        original = SAMPLE_TYPEERROR
        parse_test_failures(original)
        assert original == SAMPLE_TYPEERROR

        # Enrichment must not remove existing data or the on-disk log.
        log = tmp_path / "test-output.log"
        log.write_text(SAMPLE_TYPEERROR, encoding="utf-8")
        tool_result = ToolResult(
            success=False,
            error="failed",
            data={
                "exit_code": 1,
                "passed": 0,
                "failed": 1,
                "summary": "tail",
                "log_file": str(log),
            },
        )
        CustomAgentRunner._enrich_test_failure(tool_result)
        data = tool_result.data
        assert data is not None
        # Existing keys are untouched.
        assert data["exit_code"] == 1
        assert data["summary"] == "tail"
        assert data["log_file"] == str(log)
        # Structured failure is attached.
        assert data["test_failure"]["failed_tests"]
        # The complete log file is still intact on disk.
        assert log.read_text(encoding="utf-8") == SAMPLE_TYPEERROR


class TestRunnerIntegration:
    def test_failure_produces_structured_observation_data(
        self, tmp_path: Path
    ) -> None:
        log = tmp_path / "test-output.log"
        log.write_text(SAMPLE_TYPEERROR, encoding="utf-8")
        tool_result = ToolResult(
            success=False,
            error="failed",
            data={
                "exit_code": 1,
                "passed": 0,
                "failed": 1,
                "summary": "tail",
                "log_file": str(log),
            },
        )
        # Runner enriches the result before the observation is recorded.
        CustomAgentRunner._enrich_test_failure(tool_result)

        # State manager turns the (now enriched) result into an observation.
        state = DevPilotState(
            run_id="t", task=_make_task(), phase="implementing"
        )
        sm = StateManager(RuntimeConfig())
        sm.apply_tool_result(state, tool_result, "test.run", 10)

        obs = state.observations[-1]
        assert obs.name == "test.run"
        assert not obs.success
        failure = obs.data["test_failure"]
        assert failure["kind"] == "test_failure"
        assert "tests/api/test_orders.py::test_filter" in failure["failed_tests"]
        assert failure["errors"][0]["type"] == "TypeError"


class TestContextBlock:
    def test_context_shows_current_test_failure_block(
        self, registry
    ) -> None:
        cb = ContextBuilder(RuntimeConfig(), registry)
        failure = {
            "kind": "test_failure",
            "failed_tests": [
                "tests/api/test_orders.py::test_filter"
            ],
            "errors": [
                {
                    "type": "TypeError",
                    "message": "unexpected keyword argument 'status'",
                    "locations": ["app/services/order_service.py:45"],
                }
            ],
            "summary": "1 test(s) failed",
        }
        obs = Observation(
            step_id=1,
            source="tool",
            name="test.run",
            success=False,
            summary="failed",
            data={"test_failure": failure, "exit_code": 1},
        )
        state = DevPilotState(
            run_id="t", task=_make_task(), phase="verifying"
        )
        state.observations = [obs]
        state.repair_required = True

        messages = cb.build(state, "/workspace")
        state_msg = next(
            m for m in messages if "Current Phase" in m.content
        )
        assert "--- CURRENT TEST FAILURE ---" in state_msg.content
        assert "test_filter" in state_msg.content
        assert "TypeError" in state_msg.content
        assert "app/services/order_service.py:45" in state_msg.content
        # Generic repair block is superseded by the specific failure block.
        assert "--- REPAIR REQUIREMENT ---" not in state_msg.content
