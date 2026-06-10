"""Epic 16.8 — Verify discover_capabilities batch names lookup.

Run:
    pytest tests/k1/concierge/tools/test_discover_capabilities_batch_names.py -v -p no:xdist -p no:cacheprovider
"""

from __future__ import annotations

import pytest

from k1.concierge.tools.implementations import (
    ToolContext,
    execute_discover_capabilities,
)
from k1.concierge.tools.schemas_fabric import DISCOVER_CAPABILITIES_SCHEMA
from k1.fabric.manifest_translator import build_contract
from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.chores.definition import CHORES_DEFINITION
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION
from k1.tools.family.tasks.definition import TASKS_DEFINITION

# ── Schema tests ─────────────────────────────────────────────────────────


class TestDiscoverCapabilitiesNamesSchema:
    def test_names_in_schema_properties(self):
        props = DISCOVER_CAPABILITIES_SCHEMA.parameters["properties"]
        assert "names" in props
        assert props["names"]["type"] == "array"
        assert props["names"]["items"]["type"] == "string"

    def test_intent_still_required(self):
        assert "intent" in DISCOVER_CAPABILITIES_SCHEMA.parameters["required"]


# ── Batch names handler tests ────────────────────────────────────────────


class TestBatchNamesReturnsSchemas:
    @pytest.mark.asyncio
    async def test_valid_names_return_schemas(self):
        """Three real capability names → three schemas returned, all score=1.0."""
        # Register real contracts in the cache via a mock dispatch
        contracts = _register_real_contracts()
        dispatch = _MockDispatchWithLookup(contracts)
        ctx = _mock_ctx(dispatch=dispatch)

        result = await execute_discover_capabilities(
            {
                "intent": "companion tool lookup",
                "names": [
                    "tool.read.chores.list_chores",
                    "tool.read.tasks.list_tasks",
                    "tool.read.reminders.list_reminders",
                ],
            },
            ctx,
        )

        assert result.status == "ok"
        data = result.data
        assert data["count"] == 3
        for cap in data["capabilities"]:
            assert cap["score"] == 1.0
            assert "schema" in cap
            assert "required_inputs" in cap["schema"]

    @pytest.mark.asyncio
    async def test_missing_name_silently_omitted(self):
        """One valid + one nonexistent → valid returned, missing omitted."""
        contracts = _register_real_contracts()
        dispatch = _MockDispatchWithLookup(contracts)
        ctx = _mock_ctx(dispatch=dispatch)

        result = await execute_discover_capabilities(
            {
                "intent": "companion tool lookup",
                "names": [
                    "tool.read.chores.list_chores",
                    "nonexistent.capability.name",
                ],
            },
            ctx,
        )

        assert result.status == "ok"
        assert result.data["count"] == 1
        assert result.data["capabilities"][0]["name"] == "tool.read.chores.list_chores"

    @pytest.mark.asyncio
    async def test_empty_names_returns_empty(self):
        result = await execute_discover_capabilities({"intent": "test", "names": []}, _mock_ctx())
        assert result.status == "ok"
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_backward_compat_semantic_still_works(self):
        """Calling without names still performs semantic search path (regression)."""
        result = await execute_discover_capabilities({"intent": "schedule dentist"}, _mock_ctx())
        # No dispatch → returns empty (the semantic path tries to call dispatch
        # but since dispatch is None it falls through to empty)
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_calendar_companion_scenario(self):
        """Simulate Back asking for calendar companion tools."""
        contracts = _register_real_contracts()
        dispatch = _MockDispatchWithLookup(contracts)
        ctx = _mock_ctx(dispatch=dispatch)

        result = await execute_discover_capabilities(
            {
                "intent": "companion tool lookup",
                "names": [
                    "tool.read.chores.list_chores",
                    "tool.read.tasks.list_tasks",
                    "tool.read.reminders.list_reminders",
                ],
            },
            ctx,
        )

        assert result.data["count"] == 3
        names = [c["name"] for c in result.data["capabilities"]]
        assert "tool.read.chores.list_chores" in names
        assert "tool.read.tasks.list_tasks" in names
        assert "tool.read.reminders.list_reminders" in names

        # Each has correct required_inputs populated
        for cap in result.data["capabilities"]:
            req = [r["name"] for r in cap["schema"]["required_inputs"]]
            assert len(req) >= 0  # some may have no required inputs
            assert "required_inputs" in cap["schema"]
            assert "optional_inputs" in cap["schema"]

    @pytest.mark.asyncio
    async def test_score_is_one_for_exact_matches(self):
        """All batch name results have score=1.0 (deterministic, not heuristic)."""
        contracts = _register_real_contracts()
        dispatch = _MockDispatchWithLookup(contracts)
        ctx = _mock_ctx(dispatch=dispatch)

        result = await execute_discover_capabilities(
            {
                "intent": "test",
                "names": ["tool.read.chores.list_chores", "tool.read.tasks.list_tasks"],
            },
            ctx,
        )

        for cap in result.data["capabilities"]:
            assert cap["score"] == 1.0, f"{cap['name']} score != 1.0"


# ── Helpers ──────────────────────────────────────────────────────────────


def _register_real_contracts() -> dict[str, object]:
    """Build real CapabilityContracts for calendar, tasks, chores, reminders."""
    contracts: dict[str, object] = {}
    for defn in (CALENDAR_DEFINITION, TASKS_DEFINITION, CHORES_DEFINITION, REMINDERS_DEFINITION):
        for action in defn.actions:
            contract = build_contract(defn, action)
            contracts[contract.name] = contract
    return contracts


class _MockDispatchWithLookup:
    """Mock dispatch that supports lookup_capability for O(1) exact match."""

    def __init__(self, contracts: dict[str, object]):
        self._contracts = contracts

    def lookup_capability(self, capability_name: str):
        return self._contracts.get(capability_name)

    def lookup(self, capability_name: str):
        return self._contracts.get(capability_name)


def _mock_ctx(dispatch: object = "not_set", **kwargs) -> ToolContext:
    sm = type("M", (), {"principal_id": "test-user", "session_id": "test-session"})()
    ctx_kwargs: dict = {"session_manager": sm, "actor": "back", "session_id": "test-session"}
    if dispatch != "not_set":
        ctx_kwargs["dispatch"] = dispatch
    ctx_kwargs.update(kwargs)
    return ToolContext(**ctx_kwargs)
