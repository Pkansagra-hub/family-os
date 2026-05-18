from __future__ import annotations

from typing import Any, Dict, Optional

from k1.fabric.contracts import parse_contract_body
from k1.fabric.core.context_builder import ContextBuilder
from k1.fabric.fabric import CapabilityFabric, FabricConfig
from k1.fabric.manifest_translator import build_contract
from k1.fabric.types import CapabilityContract, CapabilityRequest
from k1.tools.family.definition import ActionSpec, FieldSpec, LLMHints, ToolDefinition


class _PromptSystem:
    def __init__(self) -> None:
        self.templates: Dict[str, str] = {}

    def add(self, name: str, text: str) -> None:
        self.templates[name] = text

    def resolve(self, template_name: str) -> Optional[Dict[str, str]]:
        text = self.templates.get(template_name)
        return {"text": text} if text is not None else None

    def compile(self, template: Dict[str, str], variables: Dict[str, Any]) -> str:
        text = template["text"]
        for key, value in variables.items():
            text = text.replace(f"{{{key}}}", str(value))
        return text


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


def test_fabric_build_context_uses_contract_prompt_and_request_override() -> None:
    prompt_system = _PromptSystem()
    prompt_system.add("example_activity_v1", "Example prompt for {name}.")
    builder = ContextBuilder(prompt_system=prompt_system)
    fabric = CapabilityFabric(
        resolver=object(),
        context_builder=builder,
        validation_pipeline=object(),
        event_emitter=object(),
        registry=object(),
        provider_factory=object(),
        config=FabricConfig(),
    )
    contract = CapabilityContract(
        name="tool.execute.example.do_thing",
        version="1.0.0",
        domain=["TEST"],
        description="Example",
        provider_type="MCP",
        provider_id="example",
        prompt_template="example_activity_v1",
        activity_profile="example.v1",
    )
    request = CapabilityRequest(
        capability_name=contract.name,
        params={"name": "params name"},
        context_override={"prompt_variables": {"name": "override name"}},
        caller="test",
    )

    context = fabric._build_context(request, contract)

    assert context.prompt == "Example prompt for override name."
    assert context.session_sections["context_override"]["activity_profile"] == "example.v1"
    assert context.session_sections["context_override"]["prompt_template"] == "example_activity_v1"
