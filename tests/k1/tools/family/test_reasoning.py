"""Tests for k1.tools.family.reasoning (§E15.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from k1.tools.family.events import EventEmitter
from k1.tools.family.reasoning import (
    _build_description,
    _llm_spec_to_contract,
    build_fabric_contracts_from_http,
    build_fabric_contracts_from_registry,
)
from k1.tools.family.registry import ToolRegistry
from k1.tools.family.storage import K1FamilyStore
from tests.k1.tools.family._stubs import DemoToolService, RecordingSsePublisher

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry(tmp_path: Path) -> ToolRegistry:
    store = K1FamilyStore(str(tmp_path / "k.db"))
    emitter = EventEmitter(RecordingSsePublisher())
    reg = ToolRegistry(store.conn, emitter, fabric=None)
    reg.register_class(DemoToolService)
    return reg


# ---------------------------------------------------------------------------
# _build_description
# ---------------------------------------------------------------------------


class TestBuildDescription:
    def test_no_hints_returns_summary(self) -> None:
        assert _build_description("Do a thing.", []) == "Do a thing."

    def test_empty_string_hint_falls_back(self) -> None:
        assert _build_description("Do a thing.", ["  "]) == "Do a thing."

    def test_hint_appended_with_separator(self) -> None:
        result = _build_description("Create event.", ["When user wants to schedule something."])
        assert result == "Create event. -- When user wants to schedule something."

    def test_only_first_hint_used(self) -> None:
        result = _build_description("Sum.", ["first", "second"])
        assert "first" in result
        assert "second" not in result


# ---------------------------------------------------------------------------
# build_fabric_contracts_from_registry (in-process)
# ---------------------------------------------------------------------------


class TestBuildFabricContractsFromRegistry:
    def test_returns_one_contract_per_action(self, registry: ToolRegistry) -> None:
        contracts = build_fabric_contracts_from_registry(registry)
        action_count = len(DemoToolService.DEFINITION.actions)
        assert len(contracts) == action_count

    def test_provider_type_is_local(self, registry: ToolRegistry) -> None:
        contracts = build_fabric_contracts_from_registry(registry)
        assert all(c.provider_type == "LOCAL" for c in contracts)

    def test_provider_id_is_native(self, registry: ToolRegistry) -> None:
        contracts = build_fabric_contracts_from_registry(registry)
        assert all(c.provider_id == "k1_native_tools" for c in contracts)

    def test_capability_names_contain_adapter_id(self, registry: ToolRegistry) -> None:
        contracts = build_fabric_contracts_from_registry(registry)
        names = [c.name for c in contracts]
        assert all("demo" in n for n in names)

    def test_read_action_gets_tool_read_prefix(self, registry: ToolRegistry) -> None:
        contracts = build_fabric_contracts_from_registry(registry)
        by_name = {c.name: c for c in contracts}
        # DemoToolService has "adults_only" with kind="read"
        assert "tool.read.demo.adults_only" in by_name

    def test_write_action_gets_tool_execute_prefix(self, registry: ToolRegistry) -> None:
        contracts = build_fabric_contracts_from_registry(registry)
        by_name = {c.name: c for c in contracts}
        # "record_write" has kind="write"
        assert "tool.execute.demo.record_write" in by_name

    def test_empty_registry_returns_empty_list(self, tmp_path: Path) -> None:
        store = K1FamilyStore(str(tmp_path / "empty.db"))
        emitter = EventEmitter(RecordingSsePublisher())
        reg = ToolRegistry(store.conn, emitter, fabric=None)
        assert build_fabric_contracts_from_registry(reg) == []


# ---------------------------------------------------------------------------
# _llm_spec_to_contract
# ---------------------------------------------------------------------------


class TestLlmSpecToContract:
    def _read_spec(self) -> dict[str, Any]:
        return {
            "name": "calendar.list_events",
            "capability_name": "tool.read.calendar.list_events",
            "kind": "read",
            "description": "List calendar events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Start date"},
                    "limit": {"type": "integer", "description": "Max results"},
                },
                "required": ["start"],
            },
            "output_schema": {"type": "object"},
            "examples": [],
        }

    def _write_spec(self) -> dict[str, Any]:
        return {
            "name": "calendar.create_event",
            "capability_name": "tool.execute.calendar.create_event",
            "kind": "write",
            "description": "Create an event.",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string", "description": "Title"}},
                "required": ["title"],
            },
            "output_schema": {},
            "examples": [],
        }

    def test_capability_name_preserved(self) -> None:
        c = _llm_spec_to_contract(self._read_spec())
        assert c.name == "tool.read.calendar.list_events"

    def test_provider_type_local(self) -> None:
        c = _llm_spec_to_contract(self._read_spec())
        assert c.provider_type == "LOCAL"

    def test_provider_id_native(self) -> None:
        c = _llm_spec_to_contract(self._read_spec())
        assert c.provider_id == "k1_native_tools"

    def test_required_inputs_parsed(self) -> None:
        c = _llm_spec_to_contract(self._read_spec())
        req_names = [i.name for i in c.required_inputs]
        opt_names = [i.name for i in c.optional_inputs]
        assert "start" in req_names
        assert "limit" in opt_names

    def test_read_capability_gets_green_band(self) -> None:
        c = _llm_spec_to_contract(self._read_spec())
        assert c.safety_band_min == "GREEN"
        assert c.risk_class == "benign"

    def test_write_capability_gets_amber_band(self) -> None:
        c = _llm_spec_to_contract(self._write_spec())
        assert c.safety_band_min == "AMBER"
        assert c.risk_class == "safety_sensitive"

    def test_description_carried_through(self) -> None:
        c = _llm_spec_to_contract(self._read_spec())
        assert c.description == "List calendar events."

    def test_fallback_name_when_no_capability_name(self) -> None:
        spec = self._read_spec()
        del spec["capability_name"]
        c = _llm_spec_to_contract(spec)
        assert c.name == "calendar.list_events"


# ---------------------------------------------------------------------------
# build_fabric_contracts_from_http
# ---------------------------------------------------------------------------


class TestBuildFabricContractsFromHttp:
    _SPECS: list[dict[str, Any]] = [
        {
            "name": "calendar.list_events",
            "capability_name": "tool.read.calendar.list_events",
            "kind": "read",
            "description": "List events.",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "output_schema": {},
            "examples": [],
        },
        {
            "name": "calendar.create_event",
            "capability_name": "tool.execute.calendar.create_event",
            "kind": "write",
            "description": "Create event.",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
            "output_schema": {},
            "examples": [],
        },
    ]

    async def test_returns_contracts_for_each_spec(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=self._SPECS)

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        contracts = await build_fabric_contracts_from_http(
            ["http://test/family/calendar"], http_client=http
        )
        assert len(contracts) == 2

    async def test_contracts_from_multiple_urls(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=self._SPECS[:1])

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        contracts = await build_fabric_contracts_from_http(
            ["http://test/family/calendar", "http://test/family/tasks"],
            http_client=http,
        )
        assert len(contracts) == 2  # 1 spec × 2 adapters

    async def test_all_contracts_are_local_provider(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=self._SPECS)

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        contracts = await build_fabric_contracts_from_http(
            ["http://test/family/calendar"], http_client=http
        )
        assert all(c.provider_type == "LOCAL" for c in contracts)

    async def test_http_error_propagates(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"detail": "down"})

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        with pytest.raises(httpx.HTTPStatusError):
            await build_fabric_contracts_from_http(
                ["http://test/family/calendar"], http_client=http
            )

    async def test_empty_url_list_returns_empty(self) -> None:
        http = httpx.AsyncClient()
        contracts = await build_fabric_contracts_from_http([], http_client=http)
        assert contracts == []
