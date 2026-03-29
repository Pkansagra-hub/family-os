"""
Unit tests for Contract Parsers -- Epic 6.2.2.

Tests the parse_contract() facade and all 4 type-specific parsers:
  - ToolContractParser
  - AgentContractParser
  - PromptContractParser
  - WorkflowContractParser

Uses real parsers, real validation, real YAML fixtures. NO MOCKS.

References:
  - fabric-implementation-plan.md Milestone 6, Epic 6.2.2
  - k1/fabric/contracts/__init__.py -- parse_contract() facade
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.contracts import ContractParseError, parse_contract, parse_contract_body
from k1.fabric.core.contract_validator import ContractValidationError, ContractValidator
from k1.fabric.types import AgentContract, CapabilityContract, PromptContract, WorkflowContract
from tests.k1.fabric.helpers import FIXTURE_NAMES, FIXTURES_DIR, load_fixture_contract

# ---------------------------------------------------------------------------
# Shared validator
# ---------------------------------------------------------------------------

_validator = ContractValidator()


# ====================================================================
# parse_contract() facade -- auto-detection from YAML files
# ====================================================================


class TestParseContractFromFile:
    """parse_contract() with YAML file paths."""

    def test_parse_tool_contract(self) -> None:
        contract = load_fixture_contract("restaurant_booking")
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.execute.restaurant_booking"
        assert contract.version == "1.0.0"
        assert "FOOD" in contract.domain

    def test_parse_agent_contract(self) -> None:
        contract = load_fixture_contract("invitation_sender")
        assert isinstance(contract, AgentContract)
        assert contract.name == "agent.execute.invitation_sender"
        assert contract.provider_type == "AGENT"

    def test_parse_prompt_contract(self) -> None:
        contract = load_fixture_contract("invitation_drafter_v1")
        assert isinstance(contract, PromptContract)
        assert contract.name == "invitation_drafter_v1"
        assert len(contract.variables) == 5

    def test_parse_workflow_contract(self) -> None:
        contract = load_fixture_contract("weekly_health_check")
        assert isinstance(contract, WorkflowContract)
        assert contract.name == "workflow.run.weekly_health_check"
        assert len(contract.steps) == 2

    @pytest.mark.parametrize("name", FIXTURE_NAMES)
    def test_all_fixtures_parse_successfully(self, name: str) -> None:
        """Every YAML fixture in fixtures/ must parse without errors."""
        contract = load_fixture_contract(name)
        assert contract.name is not None and contract.name != ""

    def test_nonexistent_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_contract(FIXTURES_DIR / "nonexistent.yaml")

    def test_non_yaml_extension_raises(self) -> None:
        with pytest.raises(ContractParseError, match="Expected .yaml"):
            parse_contract(FIXTURES_DIR / "test.txt")


# ====================================================================
# parse_contract() facade -- auto-detection from dict input
# ====================================================================


class TestParseContractFromDict:
    """parse_contract() with raw dict inputs."""

    def test_auto_detect_tool_from_dict(self) -> None:
        data = {
            "tool_contract": {
                "name": "tool.execute.from_dict_tool",
                "version": "1.0.0",
                "domain": ["TEST"],
                "description": "Dict-sourced tool contract",
                "capabilities": ["test"],
                "limitations": [],
                "required_inputs": [
                    {"name": "x", "type": "STRING", "description": "input"},
                ],
                "output": {"type": "object"},
                "provider_type": "MCP",
                "provider_id": "test",
                "safety_band_min": "GREEN",
                "availability": "ONLINE",
            }
        }
        contract = parse_contract(data, validator=_validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.execute.from_dict_tool"

    def test_auto_detect_agent_from_dict(self) -> None:
        data = {
            "agent_contract": {
                "name": "agent.execute.from_dict_agent",
                "version": "1.0.0",
                "domain": ["TEST"],
                "description": "Dict-sourced agent contract",
                "capabilities": ["test"],
                "limitations": [],
                "required_inputs": [
                    {"name": "x", "type": "STRING", "description": "input"},
                ],
                "output": {"type": "object"},
                "provider_type": "AGENT",
                "provider_id": "test",
                "safety_band_min": "GREEN",
                "availability": "ONLINE",
                "prompt_template": "test_v1",
                "tools_granted": [],
                "llm_budget_tokens": 1024,
                "max_tool_calls": 3,
                "max_execution_time_ms": 10000,
            }
        }
        contract = parse_contract(data, validator=_validator)
        assert isinstance(contract, AgentContract)

    def test_unknown_root_key_raises(self) -> None:
        with pytest.raises(ContractParseError, match="Cannot detect"):
            parse_contract({"unknown_contract": {}}, validator=_validator)

    def test_empty_dict_raises(self) -> None:
        with pytest.raises(ContractParseError, match="Cannot detect"):
            parse_contract({}, validator=_validator)


# ====================================================================
# parse_contract_body() -- explicit contract type
# ====================================================================


class TestParseContractBody:
    """parse_contract_body() with unwrapped body dicts."""

    def test_parse_tool_body(self) -> None:
        body = {
            "name": "tool.execute.body_tool",
            "version": "1.0.0",
            "domain": ["TEST"],
            "description": "Body-sourced tool",
            "capabilities": ["test"],
            "limitations": [],
            "required_inputs": [
                {"name": "x", "type": "STRING", "description": "input"},
            ],
            "output": {"type": "object"},
            "provider_type": "MCP",
            "provider_id": "test",
            "safety_band_min": "GREEN",
            "availability": "ONLINE",
        }
        contract = parse_contract_body(body, "tool_contract", validator=_validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.execute.body_tool"

    def test_parse_prompt_body(self) -> None:
        body = {
            "name": "body_prompt_v1",
            "version": "1.0.0",
            "domain": ["TEST"],
            "description": "Body-sourced prompt",
            "variables": [
                {
                    "name": "x",
                    "type": "STRING",
                    "required": True,
                    "description": "input",
                },
            ],
            "template_file": "k1/prompts/test.txt",
            "max_tokens": 1024,
            "output_format": "TEXT",
        }
        contract = parse_contract_body(body, "prompt_contract", validator=_validator)
        assert isinstance(contract, PromptContract)
        assert contract.name == "body_prompt_v1"

    def test_unknown_contract_type_raises(self) -> None:
        with pytest.raises(ContractParseError, match="Unknown contract type"):
            parse_contract_body({}, "nonexistent_type", validator=_validator)


# ====================================================================
# Validation failures during parse
# ====================================================================


class TestParseValidationFailures:
    """Contracts that fail validation raise ContractValidationError."""

    def test_invalid_name_during_parse(self) -> None:
        data = {
            "tool_contract": {
                "name": "INVALID_NAME",
                "version": "1.0.0",
                "domain": ["TEST"],
                "description": "Invalid name tool",
                "capabilities": ["test"],
                "limitations": [],
                "required_inputs": [
                    {"name": "x", "type": "STRING", "description": "input"},
                ],
                "output": {"type": "object"},
                "provider_type": "MCP",
                "provider_id": "test",
                "safety_band_min": "GREEN",
            }
        }
        with pytest.raises(ContractValidationError):
            parse_contract(data, validator=_validator)

    def test_skip_validation_bypasses_rules(self) -> None:
        data = {
            "tool_contract": {
                "name": "INVALID_NAME",
                "version": "1.0.0",
                "domain": ["TEST"],
                "description": "Invalid name but skip validation",
                "capabilities": ["test"],
                "limitations": [],
                "required_inputs": [
                    {"name": "x", "type": "STRING", "description": "input"},
                ],
                "output": {"type": "object"},
                "provider_type": "MCP",
                "provider_id": "test",
                "safety_band_min": "GREEN",
            }
        }
        # skip_validation=True should not raise
        contract = parse_contract(data, validator=_validator, skip_validation=True)
        assert isinstance(contract, CapabilityContract)


# ====================================================================
# Malformed YAML handling
# ====================================================================


class TestMalformedYaml:
    """parse_contract() handles YAML edge cases."""

    def test_invalid_yaml_syntax(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("key: [unclosed\nother: value", encoding="utf-8")
        with pytest.raises(ContractParseError, match="Invalid YAML"):
            parse_contract(bad_yaml)

    def test_yaml_with_list_root(self, tmp_path: Path) -> None:
        """YAML root should be a mapping, not a list."""
        list_yaml = tmp_path / "list.yaml"
        list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ContractParseError, match="Expected YAML mapping"):
            parse_contract(list_yaml)

    def test_yaml_with_scalar_root(self, tmp_path: Path) -> None:
        scalar_yaml = tmp_path / "scalar.yaml"
        scalar_yaml.write_text("just_a_string", encoding="utf-8")
        with pytest.raises(ContractParseError, match="Expected YAML mapping"):
            parse_contract(scalar_yaml)


# ====================================================================
# Contract dataclass roundtrip
# ====================================================================


class TestContractDataclassRoundtrip:
    """Parse YAML -> dataclass and verify field correctness."""

    def test_tool_contract_fields(self) -> None:
        contract = load_fixture_contract("restaurant_booking")
        assert isinstance(contract, CapabilityContract)
        assert contract.version == "1.0.0"
        assert contract.provider_type == "MCP"
        assert contract.provider_id == "mcp-opentable"
        assert "FOOD" in contract.domain
        assert "SOCIAL" in contract.domain
        assert len(contract.required_inputs) == 3
        assert contract.safety_band_min == "GREEN"

    def test_agent_contract_fields(self) -> None:
        contract = load_fixture_contract("invitation_sender")
        assert isinstance(contract, AgentContract)
        assert contract.provider_type == "AGENT"
        assert "tool.execute.restaurant_booking" in contract.tools_granted
        assert contract.llm_budget_tokens == 4096
        assert contract.max_tool_calls == 5

    def test_prompt_contract_fields(self) -> None:
        contract = load_fixture_contract("invitation_drafter_v1")
        assert isinstance(contract, PromptContract)
        assert contract.max_tokens == 2048
        assert contract.output_format == "TEXT"
        var_names = [v.name for v in contract.variables]
        assert "event_name" in var_names
        assert "tone" in var_names

    def test_workflow_contract_fields(self) -> None:
        contract = load_fixture_contract("weekly_health_check")
        assert isinstance(contract, WorkflowContract)
        assert contract.trigger is not None
        assert contract.trigger.type == "cron"
        assert contract.trigger.schedule == "0 8 * * MON"
        assert len(contract.steps) == 2
        step_ids = [s.id for s in contract.steps]
        assert "s1" in step_ids
        assert "s2" in step_ids
        assert contract.max_depth == 3
        assert contract.active is True

    def test_weather_tool_contract(self) -> None:
        contract = load_fixture_contract("weather_api")
        assert isinstance(contract, CapabilityContract)
        assert contract.provider_type == "WASM"
        assert "WEATHER" in contract.domain

    def test_health_agent_contract(self) -> None:
        contract = load_fixture_contract("health_summarizer")
        assert isinstance(contract, AgentContract)
        assert contract.safety_band_min == "AMBER"
        assert "HEALTH" in contract.domain


# ====================================================================
# Shared validator caching
# ====================================================================


class TestValidatorSharing:
    """Shared validator used across multiple parses for schema caching."""

    def test_shared_validator_parses_multiple_types(self) -> None:
        """Single validator instance can parse all 4 contract types."""
        shared = ContractValidator()
        tool = parse_contract(FIXTURES_DIR / "restaurant_booking.yaml", validator=shared)
        agent = parse_contract(FIXTURES_DIR / "invitation_sender.yaml", validator=shared)
        prompt = parse_contract(FIXTURES_DIR / "invitation_drafter_v1.yaml", validator=shared)
        workflow = parse_contract(FIXTURES_DIR / "weekly_health_check.yaml", validator=shared)

        assert isinstance(tool, CapabilityContract)
        assert isinstance(agent, AgentContract)
        assert isinstance(prompt, PromptContract)
        assert isinstance(workflow, WorkflowContract)
