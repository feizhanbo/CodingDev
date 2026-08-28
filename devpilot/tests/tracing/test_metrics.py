"""Tests for MetricsCollector."""

from __future__ import annotations

import time

from devpilot.tracing import MetricsCollector


class TestRecordToolCall:
    def test_increments_tool_calls(self) -> None:
        m = MetricsCollector()
        m.record_tool_call(success=True)
        m.record_tool_call(success=True)
        assert m.tool_calls == 2
        assert m.tool_failures == 0

    def test_increments_failures(self) -> None:
        m = MetricsCollector()
        m.record_tool_call(success=True)
        m.record_tool_call(success=False)
        m.record_tool_call(success=False)
        assert m.tool_calls == 3
        assert m.tool_failures == 2


class TestToolFailureRate:
    def test_zero_calls(self) -> None:
        m = MetricsCollector()
        d = m.to_dict()
        assert d["tool_failure_rate"] == 0.0

    def test_all_success(self) -> None:
        m = MetricsCollector()
        for _ in range(5):
            m.record_tool_call(success=True)
        d = m.to_dict()
        assert d["tool_failure_rate"] == 0.0

    def test_mixed(self) -> None:
        m = MetricsCollector()
        for _ in range(3):
            m.record_tool_call(success=True)
        for _ in range(2):
            m.record_tool_call(success=False)
        d = m.to_dict()
        assert d["tool_calls"] == 5
        assert d["tool_failure_rate"] == 0.4


class TestRecordTestRetry:
    def test_increments(self) -> None:
        m = MetricsCollector()
        m.record_test_retry()
        m.record_test_retry()
        assert m.test_retries == 2

    def test_reflected_in_to_dict(self) -> None:
        m = MetricsCollector()
        m.record_test_retry()
        d = m.to_dict()
        assert d["test_retries"] == 1


class TestRecordFinishRejected:
    def test_increments(self) -> None:
        m = MetricsCollector()
        m.record_finish_rejected()
        m.record_finish_rejected()
        m.record_finish_rejected()
        assert m.finish_rejected_count == 3

    def test_reflected_in_to_dict(self) -> None:
        m = MetricsCollector()
        m.record_finish_rejected()
        d = m.to_dict()
        assert d["finish_rejected_count"] == 1


class TestRecordTokens:
    def test_accumulates(self) -> None:
        m = MetricsCollector()
        m.record_tokens(100)
        m.record_tokens(200)
        assert m.tokens_used == 300

    def test_reflected_in_to_dict(self) -> None:
        m = MetricsCollector()
        m.record_tokens(500)
        d = m.to_dict()
        assert d["tokens"] == 500


class TestRecordModifiedFile:
    def test_adds_file(self) -> None:
        m = MetricsCollector()
        m.record_modified_file("app.py")
        m.record_modified_file("test.py")
        assert len(m.modified_files) == 2

    def test_no_duplicates(self) -> None:
        m = MetricsCollector()
        m.record_modified_file("app.py")
        m.record_modified_file("app.py")
        assert len(m.modified_files) == 1

    def test_reflected_in_to_dict(self) -> None:
        m = MetricsCollector()
        for i in range(5):
            m.record_modified_file(f"file_{i}.py")
        d = m.to_dict()
        assert d["modified_files"] == 5


class TestToDict:
    def test_returns_all_fields(self) -> None:
        m = MetricsCollector()
        d = m.to_dict()
        expected_keys = {
            "total_steps", "tool_calls", "tool_failure_rate",
            "test_retries", "modified_files", "duration_ms",
            "tokens", "finish_rejected_count",
        }
        assert set(d.keys()) == expected_keys

    def test_duration_ms_when_start_time_set(self) -> None:
        m = MetricsCollector()
        m.start_time = time.time()
        time.sleep(0.01)
        d = m.to_dict()
        assert d["duration_ms"] > 0

    def test_duration_ms_zero_when_not_started(self) -> None:
        m = MetricsCollector()
        d = m.to_dict()
        assert d["duration_ms"] == 0

    def test_total_steps(self) -> None:
        m = MetricsCollector()
        m.total_steps = 42
        d = m.to_dict()
        assert d["total_steps"] == 42
