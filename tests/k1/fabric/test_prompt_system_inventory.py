"""Production prompt inventory tests for Fabric PromptSystemProdAdapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from k1.fabric.adapters.prompt_system_prod import PromptSystemProdAdapter
from k1.fabric.contracts import parse_contract
from k1.fabric.contracts.prompt_contract import PromptContractParser

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = ROOT / "k1" / "contracts" / "prompts"
TOOLS_DIR = ROOT / "k1" / "contracts" / "tools"

EXPECTED_TEMPLATES = {
    "calendar_activity_v1",
    "chores_activity_v1",
    "mcp_generic_activity_v1",
    "tasks_activity_v1",
    "reminders_activity_v1",
    "shopping_activity_v1",
    "system_of_record_generic_v1",
    "wasm_generic_activity_v1",
}

EXPECTED_ACTIVITY_PROFILES = {
    "calendar_activity_v1": "calendar.v1",
    "chores_activity_v1": "chores.v1",
    "mcp_generic_activity_v1": "mcp.generic.v1",
    "tasks_activity_v1": "tasks.v1",
    "reminders_activity_v1": "reminders.v1",
    "shopping_activity_v1": "shopping.v1",
    "system_of_record_generic_v1": "system_of_record.generic.v1",
    "wasm_generic_activity_v1": "wasm.generic.v1",
}

EXPECTED_TOOL_PROFILE_METADATA = {
    "find_prompts.yaml": ("MCP", "mcp.generic.v1", "mcp_generic_activity_v1"),
    "discover_capabilities.yaml": ("MCP", "mcp.generic.v1", "mcp_generic_activity_v1"),
    "build_agent.yaml": ("MCP", "mcp.generic.v1", "mcp_generic_activity_v1"),
    "date_calc.yaml": ("WASM", "wasm.generic.v1", "wasm_generic_activity_v1"),
    "unit_convert.yaml": ("WASM", "wasm.generic.v1", "wasm_generic_activity_v1"),
}


def _prompt_contract_body(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    body = data.get("prompt_contract")
    assert isinstance(body, dict)
    return body


def test_production_prompt_inventory_loads_expected_templates() -> None:
    adapter = PromptSystemProdAdapter(CONTRACTS_DIR)

    assert EXPECTED_TEMPLATES.issubset(set(adapter.list_names()))
    assert adapter.template_count >= len(EXPECTED_TEMPLATES)

    for template_name in EXPECTED_TEMPLATES:
        template = adapter.resolve(template_name)
        assert template is not None
        assert template.template.strip()
        assert "{{template_file:" not in template.template
        assert template.metadata["template_source"] == "template_file"
        assert template.metadata["activity_profile"] == EXPECTED_ACTIVITY_PROFILES[template_name]
        assert Path(template.metadata["template_file_resolved"]).is_file()


def test_production_prompt_contracts_use_external_template_files() -> None:
    contract_files = sorted(CONTRACTS_DIR.glob("*.yaml"))
    assert contract_files

    for path in contract_files:
        body = _prompt_contract_body(path)
        assert "template" not in body
        template_file = body.get("template_file")
        assert isinstance(template_file, str) and template_file
        assert (ROOT / template_file).is_file()


def test_production_prompt_contracts_parse_against_schema() -> None:
    parser = PromptContractParser()

    for path in sorted(CONTRACTS_DIR.glob("*.yaml")):
        contract = parser.parse(path)
        assert contract.name in EXPECTED_TEMPLATES
        assert contract.activity_profile == EXPECTED_ACTIVITY_PROFILES[contract.name]
        assert contract.template_file.startswith("k1/prompts/activities/")


def test_representative_mcp_and_wasm_tool_contracts_declare_profiles() -> None:
    for filename, (
        provider_type,
        activity_profile,
        prompt_template,
    ) in EXPECTED_TOOL_PROFILE_METADATA.items():
        contract = parse_contract(TOOLS_DIR / filename)

        assert getattr(contract, "provider_type", None) == provider_type
        assert getattr(contract, "activity_profile", None) == activity_profile
        assert getattr(contract, "prompt_template", None) == prompt_template
        assert getattr(contract, "tool_instructions", None)
