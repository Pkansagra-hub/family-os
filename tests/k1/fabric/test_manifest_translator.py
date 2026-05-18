"""Unit tests for ``k1.fabric.manifest_translator``."""

from __future__ import annotations

from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.manifest_translator import (
    NATIVE_PROVIDER_ID,
    NATIVE_PROVIDER_TYPE,
    build_contract,
    register_definition,
)
from k1.tools.family.definition import ActionSpec, FieldSpec, LLMHints, ToolDefinition
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

    def test_prompt_profile_metadata_propagates_from_action(self) -> None:
        action = ActionSpec(
            name="create_item",
            kind="write",
            summary="Create an item",
            params=[FieldSpec(name="title", type="string", required=True)],
            result=[FieldSpec(name="id", type="string", required=True)],
            prompt_template="demo_activity_v1",
            activity_profile="demo.action.v1",
            tool_instructions="Use exact schema fields and preserve the returned id.",
            social_act="create_record",
            side_effects=[{"kind": "data_write", "target": "demo.item"}],
        )
        definition = ToolDefinition(
            adapter_id="demo",
            summary="Demo adapter",
            tables_sql="CREATE TABLE IF NOT EXISTS demo_schema_version (version INTEGER);",
            activity_profile="demo.default.v1",
            domain_tags=["coordination"],
            actions=[action],
        )

        contract = build_contract(definition, action)

        assert contract.prompt_template == "demo_activity_v1"
        assert contract.activity_profile == "demo.action.v1"
        assert contract.tool_instructions == "Use exact schema fields and preserve the returned id."
        assert contract.social_act == "create_record"
        assert contract.side_effects == [{"kind": "data_write", "target": "demo.item"}]
        assert "coordination" in contract.domain

    def test_definition_profile_and_llm_examples_fill_contract_defaults(self) -> None:
        action = ActionSpec(
            name="summarize_item",
            kind="compute",
            summary="Summarize an item",
            llm=LLMHints(examples=["Summarize the soccer checklist"]),
        )
        definition = ToolDefinition(
            adapter_id="demo",
            summary="Demo adapter",
            tables_sql="CREATE TABLE IF NOT EXISTS demo_schema_version (version INTEGER);",
            activity_profile="demo.default.v1",
            domain_tags=["coordination", "demo"],
            actions=[action],
        )

        contract = build_contract(definition, action)

        assert contract.activity_profile == "demo.default.v1"
        assert contract.tool_instructions == "Examples: Summarize the soccer checklist"
        assert contract.domain == ["family", "demo", "coordination"]


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
