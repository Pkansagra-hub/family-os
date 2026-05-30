"""M6 tests for metadata-only capability binding."""

from __future__ import annotations

import pytest

from k1.concierge.react.capability_routing import (
    CapabilityBindingRequest,
    bind_capability,
)
from k1.fabric.types import CapabilityContract, RetrievalResult, ScoredCapability


def _retrieval(*contracts: CapabilityContract) -> RetrievalResult:
    return RetrievalResult(
        capabilities=[
            ScoredCapability(contract=contract, score=1.0 - index * 0.1)
            for index, contract in enumerate(contracts)
        ],
        total_matched=len(contracts),
    )


@pytest.mark.asyncio
async def test_exact_candidate_binds_with_prompt_profile_metadata() -> None:
    contract = CapabilityContract(
        name="tool.execute.tasks.create_task",
        description="Create task",
        domain=["tasks"],
        prompt_template="tasks_activity_v1",
        activity_profile="tasks.v1",
    )

    async def discover(**kwargs):
        return _retrieval(contract)

    result = await bind_capability(
        CapabilityBindingRequest(
            action="tool.execute.tasks.create_task",
            candidate_capability_name="tool.execute.tasks.create_task",
            params={"title": "Clean room"},
        ),
        discover,
    )

    assert result.status == "bound"
    assert result.capability_name == "tool.execute.tasks.create_task"
    assert result.prompt_template == "tasks_activity_v1"
    assert result.activity_profile == "tasks.v1"
    assert result.context_override == {"activity_profile": "tasks.v1"}


@pytest.mark.asyncio
async def test_exact_lookup_binds_even_when_semantic_discovery_misses_slug() -> None:
    contract = CapabilityContract(
        name="tool.read.shopping.list_lists",
        description="Return shopping lists",
        domain=["family", "shopping"],
        prompt_template="shopping_activity_v1",
        activity_profile="shopping.v1",
    )

    async def discover(**kwargs):  # noqa: ARG001
        return _retrieval(
            CapabilityContract(
                name="tool.execute.shopping.add_item",
                description="Add shopping item",
                domain=["shopping"],
            )
        )

    async def exact_lookup(name: str):
        return contract if name == contract.name else None

    result = await bind_capability(
        CapabilityBindingRequest(
            action="tool.read.shopping.list_lists",
            candidate_capability_name="tool.read.shopping.list_lists",
            params={"category": "groceries"},
        ),
        discover,
        exact_lookup,
    )

    assert result.status == "bound"
    assert result.capability_name == "tool.read.shopping.list_lists"
    assert result.reason == "exact_registry_lookup"
    assert result.prompt_template == "shopping_activity_v1"


@pytest.mark.asyncio
async def test_non_exact_candidate_returns_invalid_candidate_with_options() -> None:
    contract = CapabilityContract(
        name="tool.execute.tasks.create_task",
        description="Create task",
        domain=["tasks"],
    )

    async def discover(**kwargs):
        return _retrieval(contract)

    result = await bind_capability(
        CapabilityBindingRequest(
            action="tool.execute.tasks.add_task",
            candidate_capability_name="tool.execute.tasks.add_task",
        ),
        discover,
    )

    assert result.status == "invalid_candidate"
    assert result.capability_name is None
    assert result.candidates[0]["name"] == "tool.execute.tasks.create_task"
    assert result.recovery is not None
    assert result.recovery["action"] == "select_capability"
    assert result.recovery["rejected_name"] == "tool.execute.tasks.add_task"
    assert result.recovery["candidates"] == result.candidates
    assert "do not retry" in result.recovery["instruction"]


@pytest.mark.asyncio
async def test_action_without_candidate_binds_single_discovered_capability() -> None:
    contract = CapabilityContract(
        name="tool.execute.calendar.create_event",
        description="Create calendar event",
        domain=["calendar"],
    )

    async def discover(**kwargs):
        return _retrieval(contract)

    result = await bind_capability(
        CapabilityBindingRequest(action="schedule dentist", domain="calendar"),
        discover,
    )

    assert result.status == "bound"
    assert result.capability_name == "tool.execute.calendar.create_event"


@pytest.mark.asyncio
async def test_action_without_candidate_returns_ambiguous_for_multiple_options() -> None:
    async def discover(**kwargs):
        return _retrieval(
            CapabilityContract(name="tool.execute.calendar.create_event"),
            CapabilityContract(name="tool.execute.calendar.update_event"),
        )

    result = await bind_capability(
        CapabilityBindingRequest(action="calendar change", domain="calendar"),
        discover,
    )

    assert result.status == "ambiguous"
    assert [candidate["name"] for candidate in result.candidates] == [
        "tool.execute.calendar.create_event",
        "tool.execute.calendar.update_event",
    ]


@pytest.mark.asyncio
async def test_action_without_candidate_returns_not_found_for_empty_discovery() -> None:
    async def discover(**kwargs):
        return _retrieval()

    result = await bind_capability(
        CapabilityBindingRequest(action="unknown operation"),
        discover,
    )

    assert result.status == "not_found"
    assert result.candidates == []
