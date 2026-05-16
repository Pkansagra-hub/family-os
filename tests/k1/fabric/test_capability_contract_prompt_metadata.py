from __future__ import annotations

from k1.fabric.contracts import parse_contract_body
from k1.fabric.manifest_translator import build_contract
from k1.fabric.types import CapabilityContract
from k1.tools.family.definition import ActionSpec, FieldSpec, LLMHints, ToolDefinition


def test_capability_contract_round_trips_prompt_profile_metadata() -> None:
    contract = CapabilityContract(
        name="tool.execute.example.do_thing",
        version="1.0.0",
        domain=["TEST"],
        description="Example",
        provider_type="MCP",
        provider_id="example",
        prompt_template="example_activity_v1",
        activity_profile="example.v1",
        tool_instructions="Use the example carefully.",
        prompt_variables_schema={"type": "object", "properties": {"name": {"type": "string"}}},
    )

    restored = CapabilityContract.from_dict(contract.to_dict())

    assert restored.prompt_template == "example_activity_v1"
    assert restored.activity_profile == "example.v1"
    assert restored.tool_instructions == "Use the example carefully."
    assert restored.prompt_variables_schema == {
        "type": "object",
        "properties": {"name": {"type": "string"}},
    }


def test_tool_contract_parser_accepts_prompt_profile_metadata() -> None:
    contract = parse_contract_body(
        {
            "name": "tool.execute.example_do_thing",
            "version": "1.0.0",
            "domain": ["TEST"],
            "description": "Example tool",
            "capabilities": ["write"],
            "limitations": [],
            "required_inputs": [
                {"name": "name", "type": "STRING", "description": "Name"},
            ],
            "output": {"type": "object"},
            "provider_type": "MCP",
            "provider_id": "example",
            "safety_band_min": "GREEN",
            "availability": "ONLINE",
            "prompt_template": "example_activity_v1",
            "activity_profile": "example.v1",
            "tool_instructions": "Use exact schema fields.",
            "prompt_variables_schema": {"type": "object"},
        },
        "tool_contract",
    )

    assert isinstance(contract, CapabilityContract)
    assert contract.prompt_template == "example_activity_v1"
    assert contract.activity_profile == "example.v1"
    assert contract.tool_instructions == "Use exact schema fields."
    assert contract.prompt_variables_schema == {"type": "object"}


def test_family_manifest_translator_propagates_prompt_profile_metadata() -> None:
    action = ActionSpec(
        name="create_item",
        kind="write",
        summary="Create an item",
        params=[FieldSpec(name="title", type="string", required=True)],
        result=[FieldSpec(name="id", type="string", required=True)],
        llm=LLMHints(
            use_when=["Create an example item"],
            avoid_when=["Do not use for deletion"],
            examples=["Create example item named soccer"],
        ),
        prompt_template="example_activity_v1",
        activity_profile="example.action.v1",
        tool_instructions="Copy the returned id into results.",
        social_act="create_record",
        side_effects=[{"kind": "data_write", "target": "example.item"}],
    )
    definition = ToolDefinition(
        adapter_id="example",
        summary="Example adapter",
        tables_sql="CREATE TABLE example_schema_version(version INTEGER);",
        activity_profile="example.default.v1",
        domain_tags=["coordination"],
        actions=[action],
    )

    contract = build_contract(definition, action)

    assert contract.prompt_template == "example_activity_v1"
    assert contract.activity_profile == "example.action.v1"
    assert contract.tool_instructions == "Copy the returned id into results."
    assert contract.social_act == "create_record"
    assert contract.side_effects == [{"kind": "data_write", "target": "example.item"}]
    assert "coordination" in contract.domain
