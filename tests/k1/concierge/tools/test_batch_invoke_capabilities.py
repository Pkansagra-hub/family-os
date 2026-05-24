"""M8.E2 batch_invoke_capabilities execution policy."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k1.concierge.tools.implementations import (
    ToolContext,
    execute_batch_invoke_capabilities,
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


def _success(request_id: str, data: dict | None = None) -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id=request_id,
        data=data or {"ok": True},
        provider_id="test",
    )


class _Dispatch:
    def __init__(self, contracts: dict[str, CapabilityContract] | None = None) -> None:
        self.contracts = contracts or {}
        self.direct_calls = []
        self.batch_calls = []

    async def lookup_capability(self, capability_name: str, version=None):  # type: ignore[no-untyped-def]
        return self.contracts.get(capability_name)

    async def discover_capabilities(self, **kwargs):  # type: ignore[no-untyped-def]
        return RetrievalResult(capabilities=[], total_matched=0)

    async def dispatch_direct(self, request):  # type: ignore[no-untyped-def]
        self.direct_calls.append(request)
        return _success(request.request_id, {"capability_name": request.capability_name})

    async def execute_batch(self, requests, strategy="PARALLEL"):  # type: ignore[no-untyped-def]
        self.batch_calls.append((list(requests), strategy))
        return [
            _success(request.request_id, {"capability_name": request.capability_name})
            for request in requests
        ]


@pytest.mark.asyncio
async def test_read_only_invocations_use_parallel_execute_batch_in_order() -> None:
    dispatch = _Dispatch()

    result = await execute_batch_invoke_capabilities(
        {
            "invocations": [
                {"capability_name": "tool.read.tasks.list_tasks", "params": {}},
                {"capability_name": "tool.read.calendar.list_events", "params": {}},
            ]
        },
        _ctx(dispatch),
    )

    assert result.status == "ok"
    assert len(dispatch.batch_calls) == 1
    assert dispatch.batch_calls[0][1] == "PARALLEL"
    assert dispatch.direct_calls == []
    assert [row["capability_name"] for row in result.data["results"]] == [
        "tool.read.tasks.list_tasks",
        "tool.read.calendar.list_events",
    ]


@pytest.mark.asyncio
async def test_side_effect_invocations_stay_sequential() -> None:
    contracts = {
        "tool.execute.tasks.create_task": CapabilityContract(
            name="tool.execute.tasks.create_task",
            domain=["tasks"],
            capabilities=["write"],
            side_effects=[{"type": "create"}],
        ),
        "tool.execute.calendar.create_event": CapabilityContract(
            name="tool.execute.calendar.create_event",
            domain=["calendar"],
            capabilities=["write"],
            side_effects=[{"type": "create"}],
        ),
    }
    dispatch = _Dispatch(contracts)

    result = await execute_batch_invoke_capabilities(
        {
            "invocations": [
                {"capability_name": "tool.execute.tasks.create_task", "params": {}},
                {"capability_name": "tool.execute.calendar.create_event", "params": {}},
            ]
        },
        _ctx(dispatch),
    )

    assert result.status == "ok"
    assert dispatch.batch_calls == []
    assert [request.capability_name for request in dispatch.direct_calls] == [
        "tool.execute.tasks.create_task",
        "tool.execute.calendar.create_event",
    ]


@pytest.mark.asyncio
async def test_batch_invocation_normalizes_family_member_references() -> None:
    contracts = {
        "tool.execute.tasks.create_task": CapabilityContract(
            name="tool.execute.tasks.create_task",
            domain=["tasks"],
            capabilities=["write"],
            side_effects=[{"type": "create"}],
        ),
        "tool.execute.reminders.create_reminder": CapabilityContract(
            name="tool.execute.reminders.create_reminder",
            domain=["reminders"],
            capabilities=["write"],
            side_effects=[{"type": "create"}],
        ),
    }
    dispatch = _Dispatch(contracts)

    result = await execute_batch_invoke_capabilities(
        {
            "invocations": [
                {
                    "capability_name": "tool.execute.tasks.create_task",
                    "params": {"title": "clean room", "assigned_to": "Riley"},
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


@pytest.mark.asyncio
async def test_mixed_invalid_and_parallel_batch_preserves_outer_order() -> None:
    dispatch = _Dispatch()

    result = await execute_batch_invoke_capabilities(
        {
            "invocations": [
                {"capability_name": "", "params": {}},
                {"capability_name": "tool.read.tasks.list_tasks", "params": {}},
                {"capability_name": "tool.read.calendar.list_events", "params": {}},
            ]
        },
        _ctx(dispatch),
    )

    assert result.status == "ok"
    assert [row["status"] for row in result.data["results"]] == [
        "error",
        "success",
        "success",
    ]
    assert result.data["failed"] == 1
    assert len(dispatch.batch_calls) == 1
