"""M2.E2.I2 — Dispatcher Step-0 policy gate wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

from k1.concierge.llm.types import ToolCallResult
from k1.concierge.tools.dispatcher import ToolDispatcher, _build_schema_map
from k1.concierge.tools.implementations import ToolContext
from k1.concierge.tools.result_protocol import ToolResult
from k1.concierge.tools.schemas_front import FRONT_TOOL_SCHEMAS

_TOOL_NAME = "recall_memory"


def _ctx() -> ToolContext:
    return ToolContext(session_manager=MagicMock())


def _dispatcher(policy_gate=None, allowlist: set[str] | None = None) -> ToolDispatcher:
    return ToolDispatcher(
        actor="front",
        allowlist=allowlist if allowlist is not None else {_TOOL_NAME},
        tool_schemas=_build_schema_map(FRONT_TOOL_SCHEMAS),
        ctx=_ctx(),
        tier="LOW",
        policy_gate=policy_gate,
    )


def _call() -> ToolCallResult:
    return ToolCallResult(id="c1", name=_TOOL_NAME, arguments={"query": "hi"})


async def test_no_gate_baseline_unchanged() -> None:
    disp = _dispatcher(policy_gate=None)
    out = await disp.dispatch(_call())
    assert isinstance(out, ToolResult)
    assert disp.call_count == 1


async def test_gate_returning_result_short_circuits() -> None:
    captured: list[ToolCallResult] = []
    blocked = ToolResult(tool_name=_TOOL_NAME, status="error", error="blocked by test")

    async def gate(tc):
        captured.append(tc)
        return blocked

    disp = _dispatcher(policy_gate=gate)
    out = await disp.dispatch(_call())
    assert out is blocked
    assert len(captured) == 1
    assert disp.call_count == 0


async def test_gate_returning_none_passes_through() -> None:
    seen: list[str] = []

    async def gate(tc):
        seen.append(tc.name)
        return None

    disp = _dispatcher(policy_gate=gate)
    out = await disp.dispatch(_call())
    assert isinstance(out, ToolResult)
    assert seen == [_TOOL_NAME]
    assert disp.call_count == 1


async def test_gate_exception_fails_closed() -> None:
    async def gate(tc):
        raise RuntimeError("boom")

    disp = _dispatcher(policy_gate=gate)
    out = await disp.dispatch(_call())
    assert out.status == "error"
    assert "policy gate" in (out.error or "").lower()
    assert disp.call_count == 0


async def test_gate_exception_does_not_consume_budget() -> None:
    async def gate(tc):
        raise RuntimeError("boom")

    disp = _dispatcher(policy_gate=gate)
    before = disp.budget_remaining
    await disp.dispatch(_call())
    assert disp.budget_remaining == before


async def test_gate_passthrough_still_subject_to_allowlist() -> None:
    async def gate(tc):
        return None

    disp = _dispatcher(policy_gate=gate, allowlist=set())
    out = await disp.dispatch(_call())
    assert out.status == "error"
    err = (out.error or "").lower()
    assert "not allowed" in err or "allowlist" in err or "denied" in err
