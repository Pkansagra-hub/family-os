"""M0.E1.I1: ReAct per-tool timeout coverage."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import k1.concierge.react.loop as loop_mod
from k1.concierge.llm.types import ToolSchema
from k1.concierge.react.loop import react_loop
from tests.k1.concierge.conftest import make_hub_text_response, make_hub_tool_response


def _tool_schema(name: str) -> ToolSchema:
    return ToolSchema(
        name=name,
        description=f"Test tool: {name}",
        parameters={"type": "object", "properties": {}},
    )


def _config(
    *,
    tool_timeout_ms: int = 1,
    hil_capability_gate_timeout_ms: int = 120_000,
    parallel_tools_enabled: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        react=SimpleNamespace(
            parallel_tools_enabled=parallel_tools_enabled,
            front_degenerate_fallback="sorry",
            front_budget_fallback="out of budget",
            tool_timeout_ms=tool_timeout_ms,
        ),
        llm=SimpleNamespace(default_timeout_ms=30_000),
        hil_capability_gate_timeout_ms=hil_capability_gate_timeout_ms,
    )


async def _not_cancelled() -> bool:
    return False


@pytest.mark.asyncio
async def test_tool_timeout_returns_error_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung non-terminal tool becomes a typed ToolResult observation."""
    model = AsyncMock()
    model.execute.side_effect = [
        make_hub_tool_response([{"id": "call_slow", "name": "slow_tool", "arguments": {}}]),
        make_hub_text_response("done"),
    ]

    class SlowDispatcher:
        async def dispatch(self, _tool_call):  # type: ignore[no-untyped-def]
            await asyncio.Event().wait()

    messages = []
    monkeypatch.setattr(loop_mod, "get_config", lambda: _config(tool_timeout_ms=1))

    result = await react_loop(
        actor="front",
        system_prompt="Front",
        messages=messages,
        tools=[_tool_schema("slow_tool")],
        max_iterations=2,
        model=model,
        tool_dispatcher=SlowDispatcher(),  # type: ignore[arg-type]
        on_text_response=AsyncMock(),
        cancellation_check=_not_cancelled,
        trace_id="m0-timeout",
    )

    assert result.status == "complete"
    assert result.text == "done"

    tool_messages = [message for message in messages if message.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].name == "slow_tool"
    assert "tool_timeout" in tool_messages[0].content


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["invoke_capability", "batch_invoke_capabilities"])
async def test_hil_tools_use_hil_aware_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
) -> None:
    """HIL-aware tools use max(tool_timeout, hil_gate_timeout + 30s)."""
    model = AsyncMock()
    model.execute.side_effect = [
        make_hub_tool_response([{"id": "call_hil", "name": tool_name, "arguments": {}}]),
        make_hub_text_response("done"),
    ]

    class Dispatcher:
        async def dispatch(self, _tool_call):  # type: ignore[no-untyped-def]
            return None

    cfg = _config(tool_timeout_ms=1, hil_capability_gate_timeout_ms=123)
    monkeypatch.setattr(loop_mod, "get_config", lambda: cfg)

    tool_timeouts: list[float] = []

    async def fake_wait_for(awaitable, timeout: float):  # type: ignore[no-untyped-def]
        if timeout == cfg.llm.default_timeout_ms / 1000.0:
            return await awaitable
        tool_timeouts.append(timeout)
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(loop_mod.asyncio, "wait_for", fake_wait_for)

    messages = []
    result = await react_loop(
        actor="front",
        system_prompt="Front",
        messages=messages,
        tools=[_tool_schema(tool_name)],
        max_iterations=2,
        model=model,
        tool_dispatcher=Dispatcher(),  # type: ignore[arg-type]
        on_text_response=AsyncMock(),
        cancellation_check=_not_cancelled,
        trace_id="m0-hil-timeout",
    )

    assert result.status == "complete"
    assert result.text == "done"
    assert tool_timeouts == pytest.approx([30.123])
    assert any(
        message.role == "tool" and "tool_timeout after 30.1s" in message.content
        for message in messages
    )
