from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k1.concierge.ports import IDispatchPort
from k1.concierge.tools.implementations import (
    ToolContext,
    execute_batch_invoke_capabilities,
    execute_invoke_capability,
)
from k1.fabric.types import CapabilityContract, CapabilityResult, RetrievalResult


def _ctx(dispatch) -> ToolContext:  # type: ignore[no-untyped-def]
    return ToolContext(
        session_manager=MagicMock(),
        actor="back",
        dispatch=dispatch,
        session_id="sess-1",
        safety_band="AMBER",
    )


def _success(request_id: str) -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id=request_id,
        data={"ok": True},
        provider_id="test",
    )


@pytest.mark.asyncio
async def test_single_invocation_normalizes_named_family_member_reference() -> None:
    dispatch = AsyncMock(spec=IDispatchPort)
    dispatch.dispatch_direct.return_value = _success("req-1")
    ctx = _ctx(dispatch)

    result = await execute_invoke_capability(
        {
            "capability_name": "tool.execute.tasks.create_task",
            "params": {"title": "clean bedroom", "assigned_to": "Riley"},
        },
        ctx,
    )

    assert result.status == "ok"
    request = dispatch.dispatch_direct.call_args[0][0]
    assert request.params["assigned_to"] == "riley"


class _BatchDispatch:
    def __init__(self) -> None:
        self.direct_calls = []

    async def lookup_capability(self, capability_name: str, version=None):  # type: ignore[no-untyped-def]
        return CapabilityContract(
            name=capability_name,
            domain=["family"],
            capabilities=["write"],
            side_effects=[{"type": "create"}],
        )

    async def discover_capabilities(self, **kwargs):  # type: ignore[no-untyped-def]
        return RetrievalResult(capabilities=[], total_matched=0)

    async def dispatch_direct(self, request):  # type: ignore[no-untyped-def]
        self.direct_calls.append(request)
        return _success(request.request_id)


@pytest.mark.asyncio
async def test_batch_invocation_normalizes_named_family_member_references() -> None:
    dispatch = _BatchDispatch()

    result = await execute_batch_invoke_capabilities(
        {
            "invocations": [
                {
                    "capability_name": "tool.execute.tasks.create_task",
                    "params": {"title": "clean bedroom", "assignee": "Riley"},
                },
                {
                    "capability_name": "tool.execute.reminders.create_reminder",
                    "params": {"title": "take vitamins", "recipient": "Nana Liz"},
                },
            ]
        },
        _ctx(dispatch),
    )

    assert result.status == "ok"
    assert dispatch.direct_calls[0].params["assigned_to"] == "riley"
    assert dispatch.direct_calls[1].params["recipient"] == "nana_liz"
