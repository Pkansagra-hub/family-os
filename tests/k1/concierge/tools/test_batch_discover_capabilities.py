"""Multi-intent batched discover_capabilities execution path.

The Back actor receives bundled dispatch payloads carrying N
intents.  Fanning out to N separate discover_capabilities tool calls
inflates the model context window with N full capability schema
dumps -- on Vertex/Gemini this has been observed to push the
iter=1 request past the input-budget cliff and return
``finish_reason=ERROR`` with no candidates.

The kernel-grade fix is structural, not heuristic: the tool accepts
``intents=[...]`` and fans out internally via ``asyncio.gather``,
returning ONE merged ToolResult.  This file pins that contract.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k1.concierge.tools.implementations import (
    ToolContext,
    execute_discover_capabilities,
)
from k1.fabric.types import (
    CapabilityContract,
    InputSpec,
    RetrievalResult,
    ScoredCapability,
)


def _contract(name: str, domain: str) -> CapabilityContract:
    return CapabilityContract(
        name=name,
        description=f"{name} contract",
        version="1.0.0",
        provider_type="adapter",
        domain=(domain,),
        required_inputs=(),
        optional_inputs=(),
        side_effects=(),
        safety_band_min="GREEN",
    )


class _Dispatch:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def discover_capabilities(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(dict(kwargs))
        intent = str(kwargs.get("intent") or "")
        # Return a deterministic capability per intent keyword so the
        # test can verify per-intent partitioning end-to-end.
        if "reminder" in intent.lower():
            contract = _contract("tool.read.reminders.list_reminders", "reminders")
        elif "calendar" in intent.lower() or "event" in intent.lower():
            contract = _contract("tool.read.calendar.list_events", "calendar")
        elif "task" in intent.lower():
            contract = _contract("tool.read.tasks.list_tasks", "tasks")
        elif "chore" in intent.lower():
            contract = _contract("tool.read.chores.list_chores", "chores")
        else:
            return RetrievalResult(capabilities=[], total_matched=0)
        return RetrievalResult(
            capabilities=[ScoredCapability(contract=contract, score=0.9)],
            total_matched=1,
        )


def _ctx(dispatch) -> ToolContext:  # type: ignore[no-untyped-def]
    return ToolContext(
        session_manager=MagicMock(),
        actor="back",
        dispatch=dispatch,
        session_id="sess-batch-discover",
        safety_band="GREEN",
    )


@pytest.mark.asyncio
async def test_batched_intents_fan_out_in_parallel_and_merge() -> None:
    dispatch = _Dispatch()
    ctx = _ctx(dispatch)

    result = await execute_discover_capabilities(
        {
            "intents": [
                "list reminders",
                "list calendar events",
                "list tasks",
                "list chores",
            ],
        },
        ctx,
    )

    assert result.status == "ok"
    data = result.data
    assert data.get("batched") is True
    assert data.get("count") == 4
    names = {cap["name"] for cap in data["capabilities"]}
    assert names == {
        "tool.read.reminders.list_reminders",
        "tool.read.calendar.list_events",
        "tool.read.tasks.list_tasks",
        "tool.read.chores.list_chores",
    }

    intent_results = data["intent_results"]
    assert len(intent_results) == 4
    by_intent = {entry["intent"]: entry for entry in intent_results}
    # workflow v2: intent_results carries only {intent, count}; the
    # capability names live in the merged data["capabilities"] array.
    assert by_intent["list reminders"]["count"] == 1
    assert by_intent["list calendar events"]["count"] == 1
    assert "capability_names" not in by_intent["list reminders"]
    assert "capability_names" not in by_intent["list calendar events"]


@pytest.mark.asyncio
async def test_batched_intents_dedupe_by_capability_name() -> None:
    """Same capability returned for two intents appears once in merged list."""
    dispatch = _Dispatch()
    ctx = _ctx(dispatch)

    result = await execute_discover_capabilities(
        # Both phrases resolve to the calendar list capability.
        {"intents": ["list calendar events", "list events"]},
        ctx,
    )

    assert result.status == "ok"
    names = [cap["name"] for cap in result.data["capabilities"]]
    assert names.count("tool.read.calendar.list_events") == 1
    assert len(result.data["intent_results"]) == 2


@pytest.mark.asyncio
async def test_single_intent_legacy_shape_still_works() -> None:
    dispatch = _Dispatch()
    ctx = _ctx(dispatch)

    result = await execute_discover_capabilities({"intent": "list tasks"}, ctx)

    assert result.status == "ok"
    # Legacy path does NOT set batched/intent_results.
    assert "batched" not in result.data
    assert "intent_results" not in result.data
    names = [cap["name"] for cap in result.data["capabilities"]]
    assert "tool.read.tasks.list_tasks" in names


@pytest.mark.asyncio
async def test_empty_intents_list_falls_through_to_single_intent_path() -> None:
    dispatch = _Dispatch()
    ctx = _ctx(dispatch)

    # Empty intents list with no `intent` should error like the legacy
    # path (intent is required).
    result = await execute_discover_capabilities({"intents": []}, ctx)
    assert result.status == "error"
