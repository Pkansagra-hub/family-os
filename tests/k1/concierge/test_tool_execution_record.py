"""M3 ToolExecutionRecord coverage."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import k1.concierge.tools.dispatcher as dispatcher_mod
from k1.concierge.llm.types import ToolCallResult, ToolSchema
from k1.concierge.tools.dispatcher import ToolDispatcher, hash_tool_arguments
from k1.concierge.tools.implementations import ToolContext
from k1.concierge.tools.result_protocol import ToolResult


def _dispatcher() -> ToolDispatcher:
    schema = ToolSchema(
        name="fake_tool",
        description="fake",
        parameters={"type": "object", "properties": {}},
    )
    return ToolDispatcher(
        actor="front",
        allowlist={"fake_tool"},
        tool_schemas={"fake_tool": schema},
        ctx=ToolContext(session_manager=MagicMock()),
        tier="LOW",
    )


@pytest.mark.asyncio
async def test_dispatch_records_execution_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_execute(name, args, ctx):  # type: ignore[no-untyped-def]
        return ToolResult(tool_name=name, status="ok", data={"args": args})

    monkeypatch.setattr(dispatcher_mod, "execute_tool", fake_execute)
    dispatcher = _dispatcher()

    result = await dispatcher.dispatch(
        ToolCallResult(id="call-1", name="fake_tool", arguments={"b": 2, "a": 1})
    )

    assert result.status == "ok"
    records = dispatcher.get_execution_records()
    assert len(records) == 1
    record = records[0]
    assert record.tool_name == "fake_tool"
    assert record.call_id == "call-1"
    assert record.args_hash == hash_tool_arguments({"a": 1, "b": 2})
    assert record.result_status == "ok"
    assert record.retryable is False
    assert record.duration_ms >= 0
    assert dispatcher.get_call_summaries()[0].duration_ms == record.duration_ms


def test_record_timeout_adds_retryable_execution_record() -> None:
    dispatcher = _dispatcher()
    dispatcher.record_timeout(
        ToolCallResult(id="call-timeout", name="fake_tool", arguments={"x": 1}),
        timeout_ms=250,
    )

    records = dispatcher.get_execution_records()
    assert len(records) == 1
    assert records[0].result_status == "error"
    assert records[0].retryable is True
    assert records[0].timeout_ms == 250
    assert dispatcher.call_count == 1
    assert "tool_timeout" in (dispatcher.get_call_history()[0].result.error or "")
