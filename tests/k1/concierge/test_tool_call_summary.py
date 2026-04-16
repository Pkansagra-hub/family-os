"""
Phase P — Unit Tests for ToolCallSummary pipeline
==================================================

Validates:
  - ToolCallSummary construction and frozen immutability
  - to_dict() round-trip
  - _redact_sensitive hides password/token/secret/key/api_key
  - _truncate at exactly _MAX_SUMMARY_CHARS (200)
  - _build_summary from DispatchRecord
  - get_call_summaries() with 0, 1, N records + duration estimation
  - TaskComplete.tool_call_summaries serialization round-trip
  - Backward compat: old TaskComplete dicts without tool_call_summaries
"""

from __future__ import annotations

import dataclasses

import pytest

from k1.concierge.task.dispatch import TaskComplete
from k1.concierge.tools.dispatcher import (
    DispatchRecord,
    ToolCallSummary,
    _build_summary,
    _redact_sensitive,
    _truncate,
)
from k1.concierge.tools.result_protocol import ToolResult

# =========================================================================
# ToolCallSummary dataclass basics
# =========================================================================


class TestToolCallSummary:
    """ToolCallSummary construction and properties."""

    def test_construction(self):
        s = ToolCallSummary(
            tool_name="search",
            arguments_summary='{"q": "hello"}',
            status="ok",
            result_preview='{"items": []}',
            timestamp_ms=1000,
            duration_ms=50,
        )
        assert s.tool_name == "search"
        assert s.status == "ok"
        assert s.timestamp_ms == 1000
        assert s.duration_ms == 50

    def test_frozen(self):
        s = ToolCallSummary(
            tool_name="t",
            arguments_summary="",
            status="ok",
            result_preview="",
            timestamp_ms=0,
            duration_ms=0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.tool_name = "other"  # type: ignore[misc]

    def test_to_dict(self):
        s = ToolCallSummary(
            tool_name="book_hotel",
            arguments_summary='{"name": "Inn"}',
            status="ok",
            result_preview='{"booked": true}',
            timestamp_ms=5000,
            duration_ms=120,
        )
        d = s.to_dict()
        assert d == {
            "tool_name": "book_hotel",
            "arguments_summary": '{"name": "Inn"}',
            "status": "ok",
            "result_preview": '{"booked": true}',
            "timestamp_ms": 5000,
            "duration_ms": 120,
        }

    def test_to_dict_all_fields_present(self):
        s = ToolCallSummary(
            tool_name="x",
            arguments_summary="a",
            status="error",
            result_preview="e",
            timestamp_ms=1,
            duration_ms=2,
        )
        d = s.to_dict()
        assert set(d.keys()) == {
            "tool_name",
            "arguments_summary",
            "status",
            "result_preview",
            "timestamp_ms",
            "duration_ms",
        }


# =========================================================================
# _redact_sensitive
# =========================================================================


class TestRedactSensitive:
    """Sensitive key patterns are redacted."""

    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "Password",
            "PASSWORD",
            "token",
            "auth_token",
            "secret",
            "client_secret",
            "key",
            "api_key",
            "API_KEY",
        ],
    )
    def test_sensitive_keys_redacted(self, key: str):
        result = _redact_sensitive({key: "real_value", "safe": "visible"})
        assert result[key] == "***"
        assert result["safe"] == "visible"

    def test_no_sensitive_keys(self):
        args = {"city": "Sonoma", "nights": 2}
        result = _redact_sensitive(args)
        assert result == args

    def test_empty_dict(self):
        assert _redact_sensitive({}) == {}


# =========================================================================
# _truncate
# =========================================================================


class TestTruncate:
    """Truncation at 200 char boundary."""

    def test_short_text_unchanged(self):
        assert _truncate("hello") == "hello"

    def test_exactly_200_unchanged(self):
        text = "x" * 200
        assert _truncate(text) == text
        assert len(_truncate(text)) == 200

    def test_201_truncated(self):
        text = "y" * 201
        result = _truncate(text)
        assert len(result) == 200
        assert result == "y" * 200

    def test_custom_max_len(self):
        assert _truncate("abcdef", max_len=3) == "abc"

    def test_empty_string(self):
        assert _truncate("") == ""


# =========================================================================
# _build_summary
# =========================================================================


class TestBuildSummary:
    """_build_summary converts DispatchRecord -> ToolCallSummary."""

    def test_ok_result(self):
        record = DispatchRecord(
            tool_name="search",
            arguments={"query": "hotels"},
            result=ToolResult(tool_name="search", status="ok", data={"count": 5}),
            timestamp_ms=1000,
            iteration=1,
        )
        s = _build_summary(record)
        assert s.tool_name == "search"
        assert s.status == "ok"
        assert '"query": "hotels"' in s.arguments_summary
        assert '"count": 5' in s.result_preview
        assert s.timestamp_ms == 1000
        assert s.duration_ms == 0  # _build_summary sets 0; caller patches

    def test_error_result_uses_error_field(self):
        record = DispatchRecord(
            tool_name="book",
            arguments={"id": "123"},
            result=ToolResult(
                tool_name="book",
                status="error",
                data={},
                error="connection timeout",
            ),
            timestamp_ms=2000,
            iteration=2,
        )
        s = _build_summary(record)
        assert s.status == "error"
        assert "connection timeout" in s.result_preview

    def test_sensitive_args_redacted(self):
        record = DispatchRecord(
            tool_name="auth",
            arguments={"username": "alice", "password": "s3cret"},
            result=ToolResult(tool_name="auth", status="ok", data={}),
            timestamp_ms=3000,
            iteration=1,
        )
        s = _build_summary(record)
        assert "s3cret" not in s.arguments_summary
        assert "***" in s.arguments_summary
        assert '"username": "alice"' in s.arguments_summary

    def test_long_args_truncated(self):
        long_val = "z" * 300
        record = DispatchRecord(
            tool_name="t",
            arguments={"data": long_val},
            result=ToolResult(tool_name="t", status="ok", data={}),
            timestamp_ms=0,
            iteration=1,
        )
        s = _build_summary(record)
        assert len(s.arguments_summary) <= 200

    def test_long_result_truncated(self):
        long_data = {"big": "v" * 300}
        record = DispatchRecord(
            tool_name="t",
            arguments={},
            result=ToolResult(tool_name="t", status="ok", data=long_data),
            timestamp_ms=0,
            iteration=1,
        )
        s = _build_summary(record)
        assert len(s.result_preview) <= 200

    def test_empty_arguments(self):
        record = DispatchRecord(
            tool_name="ping",
            arguments={},
            result=ToolResult(tool_name="ping", status="ok", data={"pong": True}),
            timestamp_ms=0,
            iteration=1,
        )
        s = _build_summary(record)
        assert s.arguments_summary == "{}"


# =========================================================================
# ToolDispatcher.get_call_summaries
# =========================================================================


class TestGetCallSummaries:
    """get_call_summaries builds list from call_history with duration."""

    def _make_dispatcher(self, records: list[DispatchRecord]):
        """Create a minimal ToolDispatcher with injected call_history."""
        from unittest.mock import MagicMock

        from k1.concierge.tools.dispatcher import ToolDispatcher

        dispatcher = ToolDispatcher.__new__(ToolDispatcher)
        dispatcher.call_history = list(records)
        dispatcher.call_count = len(records)
        dispatcher._actor = "back"
        dispatcher._allowlist = frozenset()
        dispatcher._tool_schemas = {}
        dispatcher._tools = {}
        dispatcher._ctx = MagicMock()
        dispatcher._tier = MagicMock()
        dispatcher._bus = None
        return dispatcher

    def test_empty_history(self):
        d = self._make_dispatcher([])
        assert d.get_call_summaries() == []

    def test_single_record_duration_zero(self):
        record = DispatchRecord(
            tool_name="search",
            arguments={"q": "test"},
            result=ToolResult(tool_name="search", status="ok", data={"r": 1}),
            timestamp_ms=1000,
            iteration=1,
        )
        d = self._make_dispatcher([record])
        summaries = d.get_call_summaries()
        assert len(summaries) == 1
        assert summaries[0].tool_name == "search"
        assert summaries[0].duration_ms == 0  # last record -> 0

    def test_multiple_records_duration_estimated(self):
        r1 = DispatchRecord(
            tool_name="a",
            arguments={},
            result=ToolResult(tool_name="a", status="ok", data={}),
            timestamp_ms=1000,
            iteration=1,
        )
        r2 = DispatchRecord(
            tool_name="b",
            arguments={},
            result=ToolResult(tool_name="b", status="ok", data={}),
            timestamp_ms=1500,
            iteration=2,
        )
        r3 = DispatchRecord(
            tool_name="c",
            arguments={},
            result=ToolResult(tool_name="c", status="error", data={}, error="fail"),
            timestamp_ms=2200,
            iteration=3,
        )
        d = self._make_dispatcher([r1, r2, r3])
        summaries = d.get_call_summaries()
        assert len(summaries) == 3
        assert summaries[0].duration_ms == 500  # 1500 - 1000
        assert summaries[1].duration_ms == 700  # 2200 - 1500
        assert summaries[2].duration_ms == 0  # last record

    def test_summaries_preserve_order(self):
        records = [
            DispatchRecord(
                tool_name=f"tool_{i}",
                arguments={"i": i},
                result=ToolResult(tool_name=f"tool_{i}", status="ok", data={}),
                timestamp_ms=i * 100,
                iteration=i,
            )
            for i in range(5)
        ]
        d = self._make_dispatcher(records)
        summaries = d.get_call_summaries()
        assert [s.tool_name for s in summaries] == [f"tool_{i}" for i in range(5)]

    def test_negative_duration_clamped_to_zero(self):
        """If timestamps are out of order (shouldn't happen), clamp to 0."""
        r1 = DispatchRecord(
            tool_name="a",
            arguments={},
            result=ToolResult(tool_name="a", status="ok", data={}),
            timestamp_ms=2000,
            iteration=1,
        )
        r2 = DispatchRecord(
            tool_name="b",
            arguments={},
            result=ToolResult(tool_name="b", status="ok", data={}),
            timestamp_ms=1000,
            iteration=2,  # earlier timestamp
        )
        d = self._make_dispatcher([r1, r2])
        summaries = d.get_call_summaries()
        assert summaries[0].duration_ms == 0  # max(0, -1000) = 0


# =========================================================================
# TaskComplete serialization with tool_call_summaries
# =========================================================================


class TestTaskCompleteToolCallSummaries:
    """TaskComplete round-trip with tool_call_summaries."""

    def test_default_empty(self):
        tc = TaskComplete(task_id="task-abc")
        assert tc.tool_call_summaries == []

    def test_to_dict_omits_when_empty(self):
        tc = TaskComplete(task_id="task-abc")
        d = tc.to_dict()
        assert "tool_call_summaries" not in d

    def test_to_dict_includes_when_populated(self):
        summaries = [
            {
                "tool_name": "search",
                "status": "ok",
                "duration_ms": 100,
                "arguments_summary": "{}",
                "result_preview": "{}",
                "timestamp_ms": 0,
            },
        ]
        tc = TaskComplete(task_id="task-abc", tool_call_summaries=summaries)
        d = tc.to_dict()
        assert d["tool_call_summaries"] == summaries

    def test_round_trip(self):
        summaries = [
            {
                "tool_name": "search",
                "status": "ok",
                "duration_ms": 100,
                "arguments_summary": '{"q": "test"}',
                "result_preview": '{"r": 1}',
                "timestamp_ms": 1000,
            },
            {
                "tool_name": "book",
                "status": "error",
                "duration_ms": 0,
                "arguments_summary": '{"id": "x"}',
                "result_preview": "timeout",
                "timestamp_ms": 2000,
            },
        ]
        tc = TaskComplete(
            task_id="task-xyz",
            final_answer="done",
            tool_calls=2,
            tool_call_summaries=summaries,
        )
        d = tc.to_dict()
        restored = TaskComplete.from_dict(d)
        assert restored.tool_call_summaries == summaries
        assert restored.task_id == "task-xyz"
        assert restored.tool_calls == 2

    def test_payload_round_trip(self):
        summaries = [
            {
                "tool_name": "t",
                "status": "ok",
                "duration_ms": 0,
                "arguments_summary": "{}",
                "result_preview": "{}",
                "timestamp_ms": 0,
            },
        ]
        tc = TaskComplete(task_id="task-rt", tool_call_summaries=summaries)
        payload_bytes = tc.to_payload()
        restored = TaskComplete.from_payload(payload_bytes)
        assert restored.tool_call_summaries == summaries

    def test_backward_compat_old_dict_without_summaries(self):
        """Old payloads without tool_call_summaries deserialize cleanly."""
        old_dict = {
            "task_id": "task-old",
            "status": "success",
            "final_answer": "booked",
            "results": [],
            "tool_calls": 3,
        }
        tc = TaskComplete.from_dict(old_dict)
        assert tc.tool_call_summaries == []
        assert tc.tool_calls == 3
