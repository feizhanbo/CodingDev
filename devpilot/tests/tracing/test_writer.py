"""Tests for TraceWriter and TraceEvent."""

from __future__ import annotations

import json
from pathlib import Path

from devpilot.tracing import TraceEvent, TraceWriter


class TestTraceEventModel:
    def test_creation_with_all_fields(self) -> None:
        event = TraceEvent(
            run_id="run_1",
            step=5,
            phase="implementing",
            event="tool_call",
            tool="code.apply_patch",
            arguments_summary="patch=...",
            timestamp="2025-01-01T00:00:00+00:00",
            data={"success": True},
        )
        assert event.run_id == "run_1"
        assert event.step == 5
        assert event.phase == "implementing"
        assert event.event == "tool_call"
        assert event.tool == "code.apply_patch"
        assert event.arguments_summary == "patch=..."
        assert event.timestamp == "2025-01-01T00:00:00+00:00"
        assert event.data == {"success": True}

    def test_auto_generates_timestamp(self) -> None:
        event = TraceEvent(
            run_id="run_1",
            step=0,
            phase="understanding",
            event="run_started",
        )
        assert event.timestamp != ""
        assert len(event.timestamp) > 0
        # Should be ISO format
        assert "T" in event.timestamp

    def test_explicit_timestamp_not_overwritten(self) -> None:
        ts = "2025-06-15T12:00:00+00:00"
        event = TraceEvent(
            run_id="run_1",
            step=0,
            phase="understanding",
            event="run_started",
            timestamp=ts,
        )
        assert event.timestamp == ts

    def test_serialization_includes_timestamp(self) -> None:
        event = TraceEvent(
            run_id="run_1",
            step=0,
            phase="understanding",
            event="run_started",
        )
        data = json.loads(event.model_dump_json())
        assert "timestamp" in data
        assert data["timestamp"] == event.timestamp


class TestTraceWriter:
    def test_write_creates_trace_jsonl(self, tmp_path: Path) -> None:
        writer = TraceWriter(str(tmp_path))
        event = TraceEvent(
            run_id="run_abc",
            step=0,
            phase="understanding",
            event="run_started",
        )
        writer.write("run_abc", event)

        trace_path = tmp_path / "run_abc" / "trace.jsonl"
        assert trace_path.is_file()

    def test_write_appends_multiple_events(self, tmp_path: Path) -> None:
        writer = TraceWriter(str(tmp_path))
        writer.write_event("run_1", 0, "understanding", "run_started")
        writer.write_event("run_1", 1, "exploring", "agent_decision")
        writer.write_event("run_1", 2, "completed", "run_completed")

        trace_path = tmp_path / "run_1" / "trace.jsonl"
        lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3

    def test_events_are_valid_json(self, tmp_path: Path) -> None:
        writer = TraceWriter(str(tmp_path))
        writer.write_event(
            "run_2", 0, "understanding", "run_started",
            data={"task_id": "DEV-001"},
        )
        writer.write_event(
            "run_2", 1, "exploring", "tool_call",
            tool="repo.search_code",
            arguments_summary="query=orders",
        )

        trace_path = tmp_path / "run_2" / "trace.jsonl"
        lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
        for line in lines:
            parsed = json.loads(line)
            assert "run_id" in parsed
            assert "step" in parsed
            assert "phase" in parsed
            assert "event" in parsed
            assert "timestamp" in parsed

    def test_file_in_correct_directory(self, tmp_path: Path) -> None:
        writer = TraceWriter(str(tmp_path / "runs"))
        writer.write_event("run_xyz", 0, "understanding", "run_started")

        trace_path = tmp_path / "runs" / "run_xyz" / "trace.jsonl"
        assert trace_path.is_file()

    def test_write_event_sets_timestamp(self, tmp_path: Path) -> None:
        writer = TraceWriter(str(tmp_path))
        writer.write_event("run_ts", 0, "understanding", "run_started")

        trace_path = tmp_path / "run_ts" / "trace.jsonl"
        line = trace_path.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed["timestamp"] is not None
        assert len(parsed["timestamp"]) > 0

    def test_multiple_runs_separate_directories(
        self, tmp_path: Path
    ) -> None:
        writer = TraceWriter(str(tmp_path))
        writer.write_event("run_a", 0, "understanding", "run_started")
        writer.write_event("run_b", 0, "understanding", "run_started")

        assert (tmp_path / "run_a" / "trace.jsonl").is_file()
        assert (tmp_path / "run_b" / "trace.jsonl").is_file()
