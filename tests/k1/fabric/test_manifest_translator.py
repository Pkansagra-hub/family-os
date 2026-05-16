"""Unit tests for ``k1.fabric.manifest_translator``."""

from __future__ import annotations

from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.manifest_translator import (
    NATIVE_PROVIDER_ID,
    NATIVE_PROVIDER_TYPE,
    build_contract,
    register_definition,
)
from tests.k1.tools.family._stubs import PingToolService


class TestBuildContract:
    def test_read_action_uses_tool_read_prefix(self) -> None:
        d = PingToolService.DEFINITION
        action = d.find_action("list_pings")
        assert action is not None
        c = build_contract(d, action)
        assert c.name == "tool.read.ping.list_pings"
        assert c.provider_type == NATIVE_PROVIDER_TYPE
        assert c.provider_id == NATIVE_PROVIDER_ID
        assert "family" in c.domain
        assert "ping" in c.domain
        assert c.risk_class == "benign"

    def test_compute_action_uses_tool_execute_prefix(self) -> None:
        d = PingToolService.DEFINITION
        action = d.find_action("ping")
        assert action is not None
        c = build_contract(d, action)
        assert c.name == "tool.execute.ping.ping"
        # compute, even though it doesn't mutate, takes execute prefix per spec
        assert c.description  # llm.use_when[0] populated

    def test_required_vs_optional_inputs_split(self) -> None:
        d = PingToolService.DEFINITION
        action = d.find_action("ping")
        assert action is not None
        c = build_contract(d, action)
        # message is optional in PingToolService
        assert all(i.name != "message" for i in c.required_inputs)
        assert any(i.name == "message" for i in c.optional_inputs)

    def test_result_fields_become_output_schema(self) -> None:
        d = PingToolService.DEFINITION
        action = d.find_action("list_pings")
        assert action is not None
        c = build_contract(d, action)
        assert c.output["type"] == "object"
        assert c.output["properties"]["items"]["type"] == "array"
        assert c.output["required"] == ["items"]


class TestRegisterDefinition:
    def test_registers_every_action(self) -> None:
        registry = CapabilityRegistry()
        names = register_definition(PingToolService.DEFINITION, registry)
        assert set(names) == {
            "tool.execute.ping.ping",
            "tool.read.ping.list_pings",
        }
        # Verify they're retrievable.
        for n in names:
            assert registry.lookup(n) is not None
