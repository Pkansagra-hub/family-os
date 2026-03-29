"""
Integration tests for Phase 1 -- Calendar MCP Server.

Tests the full calendar tool stack:
  - CalendarEvent model (frozen, to_dict, from_dict)
  - CalendarStorage (SQLite CRUD, in-memory)
  - CalendarHandlers (argument validation, delegation)
  - CalendarMCPServer (JSON-RPC routing, MCP protocol)
  - Contract YAML parsing and validation

NO MOCKS -- all tests use real components with in-memory SQLite.

References:
  - fabric_tool_implementation_plan.md Phase 1, Section 3.1.4
  - tests/k1/fabric/test_providers_331_332.py (MCP test patterns)
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from k1.fabric.contracts import parse_contract
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.types import CapabilityContract, SafetyBand
from k1.tools.mcp_servers.calendar.handlers import CalendarHandlers
from k1.tools.mcp_servers.calendar.models import CalendarEvent
from k1.tools.mcp_servers.calendar.server import CalendarMCPServer
from k1.tools.mcp_servers.calendar.storage import CalendarStorage

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "k1" / "contracts" / "tools"


# =========================================================================
# Section 1: CalendarEvent model
# =========================================================================


class TestCalendarEventModel:
    """CalendarEvent frozen dataclass behavior."""

    def test_default_construction(self) -> None:
        event = CalendarEvent()
        assert event.title == ""
        assert event.start_time == ""
        assert event.end_time == ""
        assert event.location is None
        assert event.description is None
        assert event.attendees == ()
        assert event.event_id != ""  # UUID auto-generated

    def test_full_construction(self) -> None:
        event = CalendarEvent(
            event_id="evt-1",
            title="Family Dinner",
            start_time="2025-03-15T18:00:00",
            end_time="2025-03-15T20:00:00",
            location="Home",
            description="Weekly dinner",
            attendees=("Alice", "Bob"),
            created_at="2025-03-14T10:00:00Z",
        )
        assert event.event_id == "evt-1"
        assert event.title == "Family Dinner"
        assert event.attendees == ("Alice", "Bob")
        assert event.created_at == "2025-03-14T10:00:00Z"

    def test_frozen_immutability(self) -> None:
        event = CalendarEvent(title="Test")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            event.title = "Changed"  # type: ignore[misc]

    def test_to_dict_all_fields(self) -> None:
        event = CalendarEvent(
            event_id="evt-2",
            title="Meeting",
            start_time="2025-03-15T09:00:00",
            end_time="2025-03-15T10:00:00",
            location="Office",
            description="Standup",
        )
        d = event.to_dict()
        assert d["event_id"] == "evt-2"
        assert d["title"] == "Meeting"
        assert d["start_time"] == "2025-03-15T09:00:00"
        assert d["end_time"] == "2025-03-15T10:00:00"
        assert d["location"] == "Office"
        assert d["description"] == "Standup"

    def test_to_dict_none_fields_become_empty(self) -> None:
        event = CalendarEvent(event_id="evt-3", title="Quick")
        d = event.to_dict()
        assert d["location"] == ""
        assert d["description"] == ""

    def test_from_dict_roundtrip(self) -> None:
        data = {
            "event_id": "evt-4",
            "title": "Lunch",
            "start_time": "2025-03-15T12:00:00",
            "end_time": "2025-03-15T13:00:00",
            "location": "Cafe",
            "attendees": ["Alice", "Bob"],
        }
        event = CalendarEvent.from_dict(data)
        assert event.event_id == "evt-4"
        assert event.title == "Lunch"
        assert event.attendees == ("Alice", "Bob")

    def test_from_dict_missing_optional(self) -> None:
        data = {"title": "Min"}
        event = CalendarEvent.from_dict(data)
        assert event.title == "Min"
        assert event.location is None
        assert event.attendees == ()


# =========================================================================
# Section 2: CalendarStorage (SQLite, in-memory)
# =========================================================================


class TestCalendarStorage:
    """CalendarStorage CRUD with real in-memory SQLite."""

    @pytest.fixture()
    def storage(self) -> CalendarStorage:
        s = CalendarStorage(db_path=":memory:")
        yield s  # type: ignore[misc]
        s.close()

    @pytest.mark.asyncio
    async def test_create_event_basic(self, storage: CalendarStorage) -> None:
        event = await storage.create_event(
            title="Test Event",
            start_time="2025-03-15T09:00:00",
            end_time="2025-03-15T10:00:00",
        )
        assert event.title == "Test Event"
        assert event.event_id != ""
        assert event.created_at != ""

    @pytest.mark.asyncio
    async def test_create_event_all_fields(self, storage: CalendarStorage) -> None:
        event = await storage.create_event(
            title="Full Event",
            start_time="2025-03-15T09:00:00",
            end_time="2025-03-15T10:00:00",
            location="Office",
            description="Important meeting",
            attendees=["Alice", "Bob"],
        )
        assert event.location == "Office"
        assert event.description == "Important meeting"
        assert event.attendees == ("Alice", "Bob")

    @pytest.mark.asyncio
    async def test_list_events_empty(self, storage: CalendarStorage) -> None:
        events = await storage.list_events("2025-01-01", "2025-12-31")
        assert events == []

    @pytest.mark.asyncio
    async def test_list_events_after_create(self, storage: CalendarStorage) -> None:
        await storage.create_event(
            title="Event A",
            start_time="2025-03-10T09:00:00",
            end_time="2025-03-10T10:00:00",
        )
        await storage.create_event(
            title="Event B",
            start_time="2025-03-20T14:00:00",
            end_time="2025-03-20T15:00:00",
        )
        events = await storage.list_events("2025-03-01", "2025-03-31")
        assert len(events) == 2
        assert events[0].title == "Event A"
        assert events[1].title == "Event B"

    @pytest.mark.asyncio
    async def test_list_events_date_range_filter(self, storage: CalendarStorage) -> None:
        await storage.create_event(
            title="January",
            start_time="2025-01-15T09:00:00",
            end_time="2025-01-15T10:00:00",
        )
        await storage.create_event(
            title="March",
            start_time="2025-03-15T09:00:00",
            end_time="2025-03-15T10:00:00",
        )
        events = await storage.list_events("2025-03-01", "2025-03-31")
        assert len(events) == 1
        assert events[0].title == "March"

    @pytest.mark.asyncio
    async def test_list_events_max_results(self, storage: CalendarStorage) -> None:
        for i in range(10):
            await storage.create_event(
                title=f"Event {i}",
                start_time=f"2025-03-{10 + i:02d}T09:00:00",
                end_time=f"2025-03-{10 + i:02d}T10:00:00",
            )
        events = await storage.list_events("2025-03-01", "2025-03-31", max_results=3)
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_delete_existing_event(self, storage: CalendarStorage) -> None:
        event = await storage.create_event(
            title="To Delete",
            start_time="2025-03-15T09:00:00",
            end_time="2025-03-15T10:00:00",
        )
        deleted = await storage.delete_event(event.event_id)
        assert deleted is True
        remaining = await storage.list_events("2025-03-01", "2025-03-31")
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_event(self, storage: CalendarStorage) -> None:
        deleted = await storage.delete_event("nonexistent-id")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_get_event_found(self, storage: CalendarStorage) -> None:
        created = await storage.create_event(
            title="Findable",
            start_time="2025-03-15T09:00:00",
            end_time="2025-03-15T10:00:00",
        )
        found = await storage.get_event(created.event_id)
        assert found is not None
        assert found.title == "Findable"
        assert found.event_id == created.event_id

    @pytest.mark.asyncio
    async def test_get_event_not_found(self, storage: CalendarStorage) -> None:
        found = await storage.get_event("no-such-id")
        assert found is None

    @pytest.mark.asyncio
    async def test_count_events(self, storage: CalendarStorage) -> None:
        assert await storage.count_events() == 0
        await storage.create_event(
            title="One", start_time="2025-03-15T09:00:00", end_time="2025-03-15T10:00:00"
        )
        assert await storage.count_events() == 1

    @pytest.mark.asyncio
    async def test_events_sorted_by_start_time(self, storage: CalendarStorage) -> None:
        await storage.create_event(
            title="Later", start_time="2025-03-20T09:00:00", end_time="2025-03-20T10:00:00"
        )
        await storage.create_event(
            title="Earlier", start_time="2025-03-10T09:00:00", end_time="2025-03-10T10:00:00"
        )
        events = await storage.list_events("2025-03-01", "2025-03-31")
        assert events[0].title == "Earlier"
        assert events[1].title == "Later"


# =========================================================================
# Section 3: CalendarHandlers
# =========================================================================


class TestCalendarHandlers:
    """CalendarHandlers argument validation and delegation."""

    @pytest.fixture()
    def handlers(self) -> CalendarHandlers:
        storage = CalendarStorage(db_path=":memory:")
        return CalendarHandlers(storage)

    # -- list_events -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_events_returns_events_and_count(self, handlers: CalendarHandlers) -> None:
        await handlers._storage.create_event(
            title="Test", start_time="2025-03-15T09:00:00", end_time="2025-03-15T10:00:00"
        )
        result = await handlers.list_events({"start_date": "2025-03-01", "end_date": "2025-03-31"})
        assert "events" in result
        assert "count" in result
        assert result["count"] == 1
        assert len(result["events"]) == 1

    @pytest.mark.asyncio
    async def test_list_events_missing_start_date(self, handlers: CalendarHandlers) -> None:
        with pytest.raises(ValueError, match="start_date"):
            await handlers.list_events({"end_date": "2025-03-31"})

    @pytest.mark.asyncio
    async def test_list_events_missing_end_date(self, handlers: CalendarHandlers) -> None:
        with pytest.raises(ValueError, match="end_date"):
            await handlers.list_events({"start_date": "2025-03-01"})

    # -- create_event ------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_event_returns_id_and_created(self, handlers: CalendarHandlers) -> None:
        result = await handlers.create_event(
            {
                "title": "New Event",
                "start_time": "2025-03-15T09:00:00",
                "end_time": "2025-03-15T10:00:00",
            }
        )
        assert result["status"] == "created"
        assert result["event_id"] != ""

    @pytest.mark.asyncio
    async def test_create_event_missing_title(self, handlers: CalendarHandlers) -> None:
        with pytest.raises(ValueError, match="title"):
            await handlers.create_event(
                {
                    "start_time": "2025-03-15T09:00:00",
                    "end_time": "2025-03-15T10:00:00",
                }
            )

    @pytest.mark.asyncio
    async def test_create_event_missing_start_time(self, handlers: CalendarHandlers) -> None:
        with pytest.raises(ValueError, match="start_time"):
            await handlers.create_event({"title": "T", "end_time": "2025-03-15T10:00:00"})

    @pytest.mark.asyncio
    async def test_create_event_missing_end_time(self, handlers: CalendarHandlers) -> None:
        with pytest.raises(ValueError, match="end_time"):
            await handlers.create_event({"title": "T", "start_time": "2025-03-15T09:00:00"})

    @pytest.mark.asyncio
    async def test_create_event_with_optional_fields(self, handlers: CalendarHandlers) -> None:
        result = await handlers.create_event(
            {
                "title": "Full Event",
                "start_time": "2025-03-15T09:00:00",
                "end_time": "2025-03-15T10:00:00",
                "location": "Office",
                "description": "Meeting notes",
                "attendees": ["Alice", "Bob"],
            }
        )
        assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_create_event_invalid_attendees_type(self, handlers: CalendarHandlers) -> None:
        with pytest.raises(ValueError, match="attendees"):
            await handlers.create_event(
                {
                    "title": "Test",
                    "start_time": "2025-03-15T09:00:00",
                    "end_time": "2025-03-15T10:00:00",
                    "attendees": "not-a-list",
                }
            )

    # -- delete_event ------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_event_found(self, handlers: CalendarHandlers) -> None:
        create_result = await handlers.create_event(
            {
                "title": "To Delete",
                "start_time": "2025-03-15T09:00:00",
                "end_time": "2025-03-15T10:00:00",
            }
        )
        result = await handlers.delete_event({"event_id": create_result["event_id"]})
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_event_not_found(self, handlers: CalendarHandlers) -> None:
        result = await handlers.delete_event({"event_id": "nonexistent"})
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_delete_event_missing_id(self, handlers: CalendarHandlers) -> None:
        with pytest.raises(ValueError, match="event_id"):
            await handlers.delete_event({})


# =========================================================================
# Section 4: CalendarMCPServer (JSON-RPC routing)
# =========================================================================


def _rpc(
    method: str,
    *,
    id: int = 1,
    params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 request dict."""
    msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


class TestCalendarMCPServer:
    """CalendarMCPServer JSON-RPC protocol handling."""

    @pytest.fixture()
    def server(self) -> CalendarMCPServer:
        return CalendarMCPServer(db_path=":memory:")

    # -- protocol methods --------------------------------------------------

    @pytest.mark.asyncio
    async def test_initialize(self, server: CalendarMCPServer) -> None:
        response = await server.handle_message(_rpc("initialize"))
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["protocolVersion"] == "2024-11-05"
        assert "calendar-mcp" in response["result"]["serverInfo"]["name"]

    @pytest.mark.asyncio
    async def test_tools_list_returns_3_tools(self, server: CalendarMCPServer) -> None:
        response = await server.handle_message(_rpc("tools/list"))
        tools = response["result"]["tools"]
        assert len(tools) == 3
        names = {t["name"] for t in tools}
        assert names == {
            "tool.read.calendar_list_events",
            "tool.write.calendar_create_event",
            "tool.write.calendar_delete_event",
        }

    @pytest.mark.asyncio
    async def test_ping(self, server: CalendarMCPServer) -> None:
        response = await server.handle_message(_rpc("ping", id=99))
        assert "result" in response
        assert response["id"] == 99

    @pytest.mark.asyncio
    async def test_unknown_method(self, server: CalendarMCPServer) -> None:
        response = await server.handle_message(_rpc("unknown/method"))
        assert "error" in response
        assert response["error"]["code"] == -32601

    # -- tools/call: create ------------------------------------------------

    @pytest.mark.asyncio
    async def test_tools_call_create_event(self, server: CalendarMCPServer) -> None:
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.write.calendar_create_event",
                    "arguments": {
                        "title": "MCP Test",
                        "start_time": "2025-03-15T09:00:00",
                        "end_time": "2025-03-15T10:00:00",
                    },
                },
            )
        )
        content = response["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        data = json.loads(content[0]["text"])
        assert data["status"] == "created"
        assert data["event_id"] != ""

    # -- tools/call: list --------------------------------------------------

    @pytest.mark.asyncio
    async def test_tools_call_list_events(self, server: CalendarMCPServer) -> None:
        # seed
        await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.write.calendar_create_event",
                    "arguments": {
                        "title": "Listed",
                        "start_time": "2025-03-15T09:00:00",
                        "end_time": "2025-03-15T10:00:00",
                    },
                },
            )
        )
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.read.calendar_list_events",
                    "arguments": {"start_date": "2025-03-01", "end_date": "2025-03-31"},
                },
            )
        )
        data = json.loads(response["result"]["content"][0]["text"])
        assert data["count"] == 1
        assert data["events"][0]["title"] == "Listed"

    # -- tools/call: delete ------------------------------------------------

    @pytest.mark.asyncio
    async def test_tools_call_delete_event(self, server: CalendarMCPServer) -> None:
        create_resp = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.write.calendar_create_event",
                    "arguments": {
                        "title": "To Delete",
                        "start_time": "2025-03-15T09:00:00",
                        "end_time": "2025-03-15T10:00:00",
                    },
                },
            )
        )
        event_id = json.loads(create_resp["result"]["content"][0]["text"])["event_id"]
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.write.calendar_delete_event",
                    "arguments": {"event_id": event_id},
                },
            )
        )
        data = json.loads(response["result"]["content"][0]["text"])
        assert data["status"] == "deleted"

    # -- tools/call: error paths -------------------------------------------

    @pytest.mark.asyncio
    async def test_tools_call_unknown_tool(self, server: CalendarMCPServer) -> None:
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={"name": "tool.read.nonexistent", "arguments": {}},
            )
        )
        assert "error" in response
        assert response["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_tools_call_invalid_params(self, server: CalendarMCPServer) -> None:
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.read.calendar_list_events",
                    "arguments": {},  # missing required fields
                },
            )
        )
        assert "error" in response
        assert response["error"]["code"] == -32602

    # -- full CRUD cycle ---------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_crud_cycle(self, server: CalendarMCPServer) -> None:
        """End-to-end: create -> list -> delete -> list (empty)."""
        # Create
        resp = await server.handle_message(
            _rpc(
                "tools/call",
                id=20,
                params={
                    "name": "tool.write.calendar_create_event",
                    "arguments": {
                        "title": "CRUD Test",
                        "start_time": "2025-06-01T10:00:00",
                        "end_time": "2025-06-01T11:00:00",
                        "location": "Conference Room",
                    },
                },
            )
        )
        create_data = json.loads(resp["result"]["content"][0]["text"])
        assert create_data["status"] == "created"
        event_id = create_data["event_id"]

        # List -- 1 event
        resp = await server.handle_message(
            _rpc(
                "tools/call",
                id=21,
                params={
                    "name": "tool.read.calendar_list_events",
                    "arguments": {"start_date": "2025-06-01", "end_date": "2025-06-30"},
                },
            )
        )
        list_data = json.loads(resp["result"]["content"][0]["text"])
        assert list_data["count"] == 1
        assert list_data["events"][0]["event_id"] == event_id
        assert list_data["events"][0]["location"] == "Conference Room"

        # Delete
        resp = await server.handle_message(
            _rpc(
                "tools/call",
                id=22,
                params={
                    "name": "tool.write.calendar_delete_event",
                    "arguments": {"event_id": event_id},
                },
            )
        )
        del_data = json.loads(resp["result"]["content"][0]["text"])
        assert del_data["status"] == "deleted"

        # List again -- empty
        resp = await server.handle_message(
            _rpc(
                "tools/call",
                id=23,
                params={
                    "name": "tool.read.calendar_list_events",
                    "arguments": {"start_date": "2025-06-01", "end_date": "2025-06-30"},
                },
            )
        )
        empty_data = json.loads(resp["result"]["content"][0]["text"])
        assert empty_data["count"] == 0


# =========================================================================
# Section 5: Contract YAML parsing and validation
# =========================================================================


class TestCalendarContracts:
    """Parse and validate calendar contract YAML files."""

    @pytest.fixture()
    def validator(self) -> ContractValidator:
        return ContractValidator()

    # -- individual contracts ----------------------------------------------

    def test_list_events_contract_parses(self, validator: ContractValidator) -> None:
        path = CONTRACTS_DIR / "calendar_list_events.yaml"
        contract = parse_contract(path, validator=validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.read.calendar_list_events"
        assert contract.version == "1.0.0"
        assert "CALENDAR" in contract.domain
        assert contract.provider_type == "MCP"
        assert contract.safety_band_min == SafetyBand.GREEN.value

    def test_create_event_contract_parses(self, validator: ContractValidator) -> None:
        path = CONTRACTS_DIR / "calendar_create_event.yaml"
        contract = parse_contract(path, validator=validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.write.calendar_create_event"
        assert contract.safety_band_min == SafetyBand.AMBER.value
        assert len(contract.required_inputs) == 3  # title, start_time, end_time

    def test_delete_event_contract_parses(self, validator: ContractValidator) -> None:
        path = CONTRACTS_DIR / "calendar_delete_event.yaml"
        contract = parse_contract(path, validator=validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.write.calendar_delete_event"
        assert contract.safety_band_min == SafetyBand.AMBER.value
        assert len(contract.required_inputs) == 1  # event_id

    # -- output schemas ----------------------------------------------------

    def test_list_events_output_has_events_and_count(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "calendar_list_events.yaml", validator=validator)
        assert "events" in contract.output.get("properties", {})
        assert "count" in contract.output.get("properties", {})

    def test_create_event_output_has_id_and_status(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "calendar_create_event.yaml", validator=validator)
        assert "event_id" in contract.output.get("properties", {})
        assert "status" in contract.output.get("properties", {})

    # -- cross-contract invariants -----------------------------------------

    def test_all_calendar_contracts_share_provider_id(self, validator: ContractValidator) -> None:
        """All 3 calendar contracts share the same MCP provider."""
        names = [
            "calendar_list_events.yaml",
            "calendar_create_event.yaml",
            "calendar_delete_event.yaml",
        ]
        provider_ids = set()
        for name in names:
            contract = parse_contract(CONTRACTS_DIR / name, validator=validator)
            provider_ids.add(contract.provider_id)
        assert provider_ids == {"calendar_mcp_stdio"}

    def test_read_operation_is_green(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "calendar_list_events.yaml", validator=validator)
        assert contract.safety_band_min == "GREEN"

    def test_write_operations_are_amber(self, validator: ContractValidator) -> None:
        for name in ["calendar_create_event.yaml", "calendar_delete_event.yaml"]:
            contract = parse_contract(CONTRACTS_DIR / name, validator=validator)
            assert contract.safety_band_min == "AMBER"
