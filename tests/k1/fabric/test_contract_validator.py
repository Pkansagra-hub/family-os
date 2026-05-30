"""
Unit tests for ContractValidator -- Epic 6.2.1.

Tests all 12 semantic validation rules plus Phase 1 (JSON Schema).
Uses real ContractValidator (no mocks). Fixtures from conftest.py and helpers.py.

References:
  - fabric-implementation-plan.md Milestone 6, Epic 6.2.1
  - contract_validator.py -- 12 semantic rules + Phase 1 schema
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from k1.fabric.core.contract_validator import (
    ContractValidationError,
    ContractValidator,
    detect_contract_type,
)
from k1.fabric.types import CapabilityContract
from tests.k1.fabric.helpers import load_fixture_contract

# ---------------------------------------------------------------------------
# Shared validator instance (stateless, thread-safe)
# ---------------------------------------------------------------------------

_validator = ContractValidator()


# ---------------------------------------------------------------------------
# Helpers to build minimal valid contract dicts
# ---------------------------------------------------------------------------


def _minimal_tool_contract(**overrides: Any) -> Dict[str, Any]:
    """Minimal valid tool_contract dict with root key wrapper."""
    body: Dict[str, Any] = {
        "name": "tool.execute.test_tool",
        "version": "1.0.0",
        "domain": ["TEST"],
        "description": "A test tool for validation tests",
        "capabilities": ["test_action"],
        "limitations": [],
        "required_inputs": [
            {"name": "input_a", "type": "STRING", "description": "input a"},
        ],
        "output": {"type": "object"},
        "provider_type": "MCP",
        "provider_id": "test-provider",
        "safety_band_min": "GREEN",
        "availability": "ONLINE",
    }
    body.update(overrides)
    return {"tool_contract": body}


def _minimal_agent_contract(**overrides: Any) -> Dict[str, Any]:
    """Minimal valid agent_contract dict with root key wrapper."""
    body: Dict[str, Any] = {
        "name": "agent.execute.test_agent",
        "version": "1.0.0",
        "domain": ["TEST"],
        "description": "A test agent for validation tests",
        "capabilities": ["test_action"],
        "limitations": [],
        "required_inputs": [
            {"name": "input_a", "type": "STRING", "description": "input a"},
        ],
        "output": {"type": "object"},
        "provider_type": "AGENT",
        "provider_id": "test-agent-provider",
        "safety_band_min": "GREEN",
        "availability": "ONLINE",
        "prompt_template": "test_prompt_v1",
        "tools_granted": ["tool.execute.test_tool"],
        "llm_budget_tokens": 2048,
        "max_tool_calls": 5,
        "max_execution_time_ms": 30000,
    }
    body.update(overrides)
    return {"agent_contract": body}


def _minimal_prompt_contract(**overrides: Any) -> Dict[str, Any]:
    """Minimal valid prompt_contract dict with root key wrapper."""
    body: Dict[str, Any] = {
        "name": "test_prompt_v1",
        "version": "1.0.0",
        "domain": ["TEST"],
        "description": "A test prompt for validation tests",
        "variables": [
            {
                "name": "input_var",
                "type": "STRING",
                "required": True,
                "description": "test variable",
            },
        ],
        "template_file": "k1/prompts/test_prompt.txt",
        "max_tokens": 1024,
        "output_format": "TEXT",
    }
    body.update(overrides)
    return {"prompt_contract": body}


def _minimal_workflow_contract(**overrides: Any) -> Dict[str, Any]:
    """Minimal valid workflow_contract dict with root key wrapper."""
    body: Dict[str, Any] = {
        "name": "workflow.run.test_workflow",
        "version": "1.0.0",
        "domain": ["TEST"],
        "description": "A test workflow for validation tests",
        "source_plan_id": "plan-test-001",
        "trigger": {"type": "manual"},
        "steps": [
            {"id": "s1", "capability": "tool.execute.test_tool", "params": {}},
        ],
        "dependencies": {},
        "max_depth": 3,
        "allows_sub_workflows": False,
        "safety_band_min": "GREEN",
        "active": True,
    }
    body.update(overrides)
    return {"workflow_contract": body}


# ====================================================================
# detect_contract_type
# ====================================================================


class TestDetectContractType:
    """Tests for detect_contract_type() auto-detection helper."""

    def test_detects_tool(self) -> None:
        assert detect_contract_type({"tool_contract": {}}) == "tool_contract"

    def test_detects_agent(self) -> None:
        assert detect_contract_type({"agent_contract": {}}) == "agent_contract"

    def test_detects_prompt(self) -> None:
        assert detect_contract_type({"prompt_contract": {}}) == "prompt_contract"

    def test_detects_workflow(self) -> None:
        assert detect_contract_type({"workflow_contract": {}}) == "workflow_contract"

    def test_returns_none_for_unknown(self) -> None:
        assert detect_contract_type({"unknown_type": {}}) is None

    def test_returns_none_for_empty(self) -> None:
        assert detect_contract_type({}) is None


# ====================================================================
# Valid contracts pass validation (all 4 types)
# ====================================================================


class TestValidContractsPasses:
    """Valid contracts pass both Phase 1 (schema) and Phase 2 (semantic)."""

    def test_valid_tool_contract(self) -> None:
        data = _minimal_tool_contract()
        errors = _validator.validate(data)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_valid_agent_contract(self) -> None:
        data = _minimal_agent_contract()
        errors = _validator.validate(data)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_valid_prompt_contract(self) -> None:
        data = _minimal_prompt_contract()
        errors = _validator.validate(data)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_valid_workflow_contract(self) -> None:
        data = _minimal_workflow_contract()
        errors = _validator.validate(data)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_fixture_restaurant_booking_valid(self) -> None:
        """YAML fixture roundtrip: parse validates without errors."""
        contract = load_fixture_contract("restaurant_booking")
        assert contract.name == "tool.execute.restaurant_booking"

    def test_fixture_invitation_sender_valid(self) -> None:
        contract = load_fixture_contract("invitation_sender")
        assert contract.name == "agent.execute.invitation_sender"

    def test_fixture_invitation_drafter_v1_valid(self) -> None:
        contract = load_fixture_contract("invitation_drafter_v1")
        assert contract.name == "invitation_drafter_v1"

    def test_fixture_weekly_health_check_valid(self) -> None:
        contract = load_fixture_contract("weekly_health_check")
        assert contract.name == "workflow.run.weekly_health_check"


class TestCapabilityContractPromptProfileMetadata:
    """CapabilityContract preserves M1 prompt/profile metadata."""

    def test_round_trips_prompt_profile_fields(self) -> None:
        contract = CapabilityContract(
            name="tool.execute.test_tool",
            version="1.0.0",
            domain=["TEST"],
            description="Test tool",
            provider_type="MCP",
            provider_id="test-provider",
            prompt_template="test_activity_v1",
            activity_profile="test.activity.v1",
            tool_instructions="Inspect the schema before invoking.",
            prompt_variables_schema={
                "type": "object",
                "properties": {"input_a": {"type": "string"}},
                "required": ["input_a"],
            },
        )

        restored = CapabilityContract.from_dict(contract.to_dict())

        assert restored.prompt_template == "test_activity_v1"
        assert restored.activity_profile == "test.activity.v1"
        assert restored.tool_instructions == "Inspect the schema before invoking."
        assert restored.prompt_variables_schema == {
            "type": "object",
            "properties": {"input_a": {"type": "string"}},
            "required": ["input_a"],
        }

    def test_defaults_keep_prompt_profile_fields_empty(self) -> None:
        restored = CapabilityContract.from_dict(CapabilityContract().to_dict())

        assert restored.prompt_template is None
        assert restored.activity_profile is None
        assert restored.tool_instructions is None
        assert restored.prompt_variables_schema is None


# ====================================================================
# validate_or_raise
# ====================================================================


class TestValidateOrRaise:
    """Tests for validate_or_raise() convenience method."""

    def test_valid_contract_no_exception(self) -> None:
        data = _minimal_tool_contract()
        _validator.validate_or_raise(data)  # should not raise

    def test_invalid_contract_raises(self) -> None:
        data = _minimal_tool_contract(name="INVALID-NAME")
        with pytest.raises(ContractValidationError) as exc_info:
            _validator.validate_or_raise(data)
        assert len(exc_info.value.errors) > 0
        assert exc_info.value.contract_type == "tool_contract"

    def test_error_includes_contract_name(self) -> None:
        data = _minimal_tool_contract(version="bad")
        with pytest.raises(ContractValidationError) as exc_info:
            _validator.validate_or_raise(data)
        assert exc_info.value.contract_name == "tool.execute.test_tool"


# ====================================================================
# validate_body
# ====================================================================


class TestValidateBody:
    """Tests for validate_body() with unwrapped body dict."""

    def test_valid_body(self) -> None:
        data = _minimal_tool_contract()
        errors = _validator.validate_body(data["tool_contract"], "tool_contract")
        assert errors == []

    def test_invalid_body(self) -> None:
        data = _minimal_tool_contract(name="INVALID")
        errors = _validator.validate_body(data["tool_contract"], "tool_contract")
        assert any("rule-01" in e for e in errors)

    def test_unknown_contract_type(self) -> None:
        errors = _validator.validate_body({}, "nonexistent_type")
        assert any("Unknown contract type" in e for e in errors)


# ====================================================================
# Rule 1: Name convention (FAB-11)
# ====================================================================


class TestRule01NameConvention:
    """Rule 1: name must follow type-specific naming patterns."""

    @pytest.mark.parametrize(
        "name",
        [
            "tool.execute.restaurant_booking",
            "tool.read.weather_api",
            "tool.write.save_data",
            "tool.delete.remove_entry",
        ],
    )
    def test_valid_tool_names(self, name: str) -> None:
        data = _minimal_tool_contract(name=name)
        errors = _validator.validate(data)
        rule01 = [e for e in errors if "rule-01" in e]
        assert rule01 == [], f"Expected no rule-01 errors for '{name}', got: {rule01}"

    @pytest.mark.parametrize(
        "name",
        [
            "INVALID",
            "tool.EXECUTE.test",
            "tool.execute",
            "agent.execute.test",
            "tool.execute.UpperCase",
            "",
        ],
    )
    def test_invalid_tool_names(self, name: str) -> None:
        data = _minimal_tool_contract(name=name)
        errors = _validator.validate(data)
        rule01 = [e for e in errors if "rule-01" in e]
        assert len(rule01) > 0, f"Expected rule-01 error for '{name}'"

    @pytest.mark.parametrize(
        "name",
        [
            "agent.execute.invitation_sender",
            "agent.spawn.helper_agent",
        ],
    )
    def test_valid_agent_names(self, name: str) -> None:
        data = _minimal_agent_contract(name=name)
        errors = _validator.validate(data)
        rule01 = [e for e in errors if "rule-01" in e]
        assert rule01 == []

    @pytest.mark.parametrize(
        "name",
        [
            "agent.EXECUTE.test",
            "tool.execute.wrong_type",
            "AGENT.execute.test",
        ],
    )
    def test_invalid_agent_names(self, name: str) -> None:
        data = _minimal_agent_contract(name=name)
        errors = _validator.validate(data)
        rule01 = [e for e in errors if "rule-01" in e]
        assert len(rule01) > 0

    @pytest.mark.parametrize(
        "name",
        [
            "greeting_v1",
            "invitation_drafter_v1",
            "simple_prompt",
            "health_summary_v2",
        ],
    )
    def test_valid_prompt_names(self, name: str) -> None:
        data = _minimal_prompt_contract(name=name)
        errors = _validator.validate(data)
        rule01 = [e for e in errors if "rule-01" in e]
        assert rule01 == []

    @pytest.mark.parametrize(
        "name",
        [
            "workflow.run.valid_workflow",
        ],
    )
    def test_valid_workflow_names(self, name: str) -> None:
        data = _minimal_workflow_contract(name=name)
        errors = _validator.validate(data)
        rule01 = [e for e in errors if "rule-01" in e]
        assert rule01 == []

    @pytest.mark.parametrize(
        "name",
        [
            "workflow.execute.wrong_verb",
            "WORKFLOW.run.uppercase",
        ],
    )
    def test_invalid_workflow_names(self, name: str) -> None:
        data = _minimal_workflow_contract(name=name)
        errors = _validator.validate(data)
        rule01 = [e for e in errors if "rule-01" in e]
        assert len(rule01) > 0

    # ------------------------------------------------------------------
    # IFL and MCP multi-segment tool names (3+ segments supported)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "name",
        [
            # IFL 5-segment: tool.verb.category.adapter.action
            "tool.execute.home.hue.set_brightness",
            "tool.read.finance.chase.check_balance",
            "tool.execute.transport.uber.request_ride",
            "tool.execute.health.fitbit.get_heart_rate",
            # IFL 4-segment: tool.verb.category.action
            "tool.execute.home.lights",
            "tool.read.home.temperature",
            # MCP dynamic 4-segment: tool.verb.mcp.tool_name
            "tool.execute.mcp.get_weather",
            "tool.read.mcp.list_files",
            # IFL 6-segment (nested)
            "tool.execute.home.hue.bedroom.dimmer",
        ],
    )
    def test_valid_ifl_and_mcp_tool_names(self, name: str) -> None:
        """Multi-segment tool names (IFL/MCP) must pass validation."""
        data = _minimal_tool_contract(name=name)
        errors = _validator.validate(data)
        rule01 = [e for e in errors if "rule-01" in e]
        assert rule01 == [], f"Expected no rule-01 errors for '{name}', got: {rule01}"

    @pytest.mark.parametrize(
        "name",
        [
            # Only 2 segments (missing name)
            "tool.execute",
            # verb segment invalid
            "tool.invoke.home.hue.action",
            # uppercase in segments
            "tool.execute.Home.hue.action",
            "tool.execute.home.Hue.action",
        ],
    )
    def test_invalid_multi_segment_tool_names(self, name: str) -> None:
        """Multi-segment names with bad verbs or case must still fail."""
        data = _minimal_tool_contract(name=name)
        errors = _validator.validate(data)
        rule01 = [e for e in errors if "rule-01" in e]
        assert len(rule01) > 0, f"Expected rule-01 error for '{name}'"


# ====================================================================
# Rule 2: Semver
# ====================================================================


class TestRule02Semver:
    """Rule 2: version must be valid semver (major.minor.patch)."""

    @pytest.mark.parametrize("version", ["1.0.0", "0.1.0", "10.20.30"])
    def test_valid_semver(self, version: str) -> None:
        data = _minimal_tool_contract(version=version)
        errors = _validator.validate(data)
        rule02 = [e for e in errors if "rule-02" in e]
        assert rule02 == []

    @pytest.mark.parametrize("version", ["1.0", "v1.0.0", "1.0.0-beta", "abc", ""])
    def test_invalid_semver(self, version: str) -> None:
        data = _minimal_tool_contract(version=version)
        errors = _validator.validate(data)
        rule02 = [e for e in errors if "rule-02" in e]
        assert len(rule02) > 0


# ====================================================================
# Rule 3: Domain tags
# ====================================================================


class TestRule03Domain:
    """Rule 3: domain must have >= 1 non-empty tag."""

    def test_single_domain(self) -> None:
        data = _minimal_tool_contract(domain=["FOOD"])
        errors = _validator.validate(data)
        rule03 = [e for e in errors if "rule-03" in e]
        assert rule03 == []

    def test_multiple_domains(self) -> None:
        data = _minimal_tool_contract(domain=["FOOD", "SOCIAL"])
        errors = _validator.validate(data)
        rule03 = [e for e in errors if "rule-03" in e]
        assert rule03 == []

    def test_empty_domain(self) -> None:
        data = _minimal_tool_contract(domain=[])
        errors = _validator.validate(data)
        rule03 = [e for e in errors if "rule-03" in e]
        assert len(rule03) > 0

    def test_domain_with_empty_string(self) -> None:
        data = _minimal_tool_contract(domain=["FOOD", ""])
        errors = _validator.validate(data)
        rule03 = [e for e in errors if "rule-03" in e]
        assert len(rule03) > 0


# ====================================================================
# Rule 4: Description
# ====================================================================


class TestRule04Description:
    """Rule 4: description must be non-empty and <= 512 chars."""

    def test_valid_description(self) -> None:
        data = _minimal_tool_contract(description="A valid description")
        errors = _validator.validate(data)
        rule04 = [e for e in errors if "rule-04" in e]
        assert rule04 == []

    def test_empty_description(self) -> None:
        data = _minimal_tool_contract(description="")
        errors = _validator.validate(data)
        rule04 = [e for e in errors if "rule-04" in e]
        assert len(rule04) > 0

    def test_description_too_long(self) -> None:
        data = _minimal_tool_contract(description="x" * 513)
        errors = _validator.validate(data)
        rule04 = [e for e in errors if "rule-04" in e]
        assert len(rule04) > 0

    def test_description_at_limit(self) -> None:
        data = _minimal_tool_contract(description="x" * 512)
        errors = _validator.validate(data)
        rule04 = [e for e in errors if "rule-04" in e]
        assert rule04 == []


# ====================================================================
# Rule 5: Required inputs (name/type/description)
# ====================================================================


class TestRule05RequiredInputs:
    """Rule 5: required_inputs elements must have name, type, description."""

    def test_valid_inputs(self) -> None:
        data = _minimal_tool_contract()
        errors = _validator.validate(data)
        rule05 = [e for e in errors if "rule-05" in e]
        assert rule05 == []

    def test_missing_input_name(self) -> None:
        data = _minimal_tool_contract(required_inputs=[{"type": "STRING", "description": "desc"}])
        errors = _validator.validate(data)
        rule05 = [e for e in errors if "rule-05" in e]
        assert len(rule05) > 0

    def test_missing_input_type(self) -> None:
        data = _minimal_tool_contract(required_inputs=[{"name": "x", "description": "desc"}])
        errors = _validator.validate(data)
        rule05 = [e for e in errors if "rule-05" in e]
        assert len(rule05) > 0

    def test_missing_input_description(self) -> None:
        data = _minimal_tool_contract(required_inputs=[{"name": "x", "type": "STRING"}])
        errors = _validator.validate(data)
        rule05 = [e for e in errors if "rule-05" in e]
        assert len(rule05) > 0

    def test_empty_input_name(self) -> None:
        data = _minimal_tool_contract(
            required_inputs=[{"name": "", "type": "STRING", "description": "desc"}]
        )
        errors = _validator.validate(data)
        rule05 = [e for e in errors if "rule-05" in e]
        assert len(rule05) > 0


# ====================================================================
# Rule 6: Output schema (tool/agent only)
# ====================================================================


class TestRule06OutputSchema:
    """Rule 6: output must have 'type' property for tool/agent."""

    def test_valid_output(self) -> None:
        data = _minimal_tool_contract(output={"type": "object"})
        errors = _validator.validate(data)
        rule06 = [e for e in errors if "rule-06" in e]
        assert rule06 == []

    def test_output_missing_type(self) -> None:
        data = _minimal_tool_contract(output={"properties": {}})
        errors = _validator.validate(data)
        rule06 = [e for e in errors if "rule-06" in e]
        assert len(rule06) > 0

    def test_output_not_checked_for_prompt(self) -> None:
        """Prompt contracts do not have output schema, rule 6 skipped."""
        data = _minimal_prompt_contract()
        errors = _validator.validate(data)
        rule06 = [e for e in errors if "rule-06" in e]
        assert rule06 == []


# ====================================================================
# Rule 7: Provider type
# ====================================================================


class TestRule07ProviderType:
    """Rule 7: provider_type must be valid enum; tool=MCP/WASM/BRIDGE, agent=AGENT."""

    @pytest.mark.parametrize("ptype", ["MCP", "WASM", "BRIDGE"])
    def test_valid_tool_providers(self, ptype: str) -> None:
        data = _minimal_tool_contract(provider_type=ptype)
        errors = _validator.validate(data)
        rule07 = [e for e in errors if "rule-07" in e]
        assert rule07 == []

    def test_tool_cannot_use_agent_provider(self) -> None:
        data = _minimal_tool_contract(provider_type="AGENT")
        errors = _validator.validate(data)
        rule07 = [e for e in errors if "rule-07" in e]
        assert len(rule07) > 0

    def test_agent_must_use_agent_provider(self) -> None:
        data = _minimal_agent_contract(provider_type="AGENT")
        errors = _validator.validate(data)
        rule07 = [e for e in errors if "rule-07" in e]
        assert rule07 == []

    def test_agent_cannot_use_mcp_provider(self) -> None:
        data = _minimal_agent_contract(provider_type="MCP")
        errors = _validator.validate(data)
        rule07 = [e for e in errors if "rule-07" in e]
        assert len(rule07) > 0

    def test_invalid_provider_type(self) -> None:
        data = _minimal_tool_contract(provider_type="INVALID")
        errors = _validator.validate(data)
        rule07 = [e for e in errors if "rule-07" in e]
        assert len(rule07) > 0


# ====================================================================
# Rule 8: Safety band
# ====================================================================


class TestRule08SafetyBand:
    """Rule 8: safety_band_min must be GREEN/AMBER/RED/CRISIS."""

    @pytest.mark.parametrize("band", ["GREEN", "AMBER", "RED", "CRISIS"])
    def test_valid_safety_bands(self, band: str) -> None:
        data = _minimal_tool_contract(safety_band_min=band)
        errors = _validator.validate(data)
        rule08 = [e for e in errors if "rule-08" in e]
        assert rule08 == []

    def test_invalid_safety_band(self) -> None:
        data = _minimal_tool_contract(safety_band_min="YELLOW")
        errors = _validator.validate(data)
        rule08 = [e for e in errors if "rule-08" in e]
        assert len(rule08) > 0


# ====================================================================
# Rule 9: Availability
# ====================================================================


class TestRule09Availability:
    """Rule 9: availability must be ONLINE/DEGRADED/OFFLINE."""

    @pytest.mark.parametrize("avail", ["ONLINE", "DEGRADED", "OFFLINE"])
    def test_valid_availability(self, avail: str) -> None:
        data = _minimal_tool_contract(availability=avail)
        errors = _validator.validate(data)
        rule09 = [e for e in errors if "rule-09" in e]
        assert rule09 == []

    def test_invalid_availability(self) -> None:
        data = _minimal_tool_contract(availability="DOWN")
        errors = _validator.validate(data)
        rule09 = [e for e in errors if "rule-09" in e]
        assert len(rule09) > 0


# ====================================================================
# Rule 10: Agent tools_granted
# ====================================================================


class TestRule10AgentToolsGranted:
    """Rule 10: agent tools_granted must reference valid tool names."""

    def test_valid_tools_granted(self) -> None:
        data = _minimal_agent_contract(
            tools_granted=["tool.execute.restaurant_booking", "tool.read.weather_api"]
        )
        errors = _validator.validate(data)
        rule10 = [e for e in errors if "rule-10" in e]
        assert rule10 == []

    def test_invalid_tool_name_in_granted(self) -> None:
        data = _minimal_agent_contract(tools_granted=["not_a_valid_tool_name"])
        errors = _validator.validate(data)
        rule10 = [e for e in errors if "rule-10" in e]
        assert len(rule10) > 0

    def test_empty_tool_name_in_granted(self) -> None:
        data = _minimal_agent_contract(tools_granted=[""])
        errors = _validator.validate(data)
        rule10 = [e for e in errors if "rule-10" in e]
        assert len(rule10) > 0

    def test_rule_only_applies_to_agent(self) -> None:
        """Tool contracts with tools_granted should not trigger rule 10."""
        data = _minimal_tool_contract()
        data["tool_contract"]["tools_granted"] = ["bad_name"]
        errors = _validator.validate(data)
        rule10 = [e for e in errors if "rule-10" in e]
        assert rule10 == []


# ====================================================================
# Rule 11: Prompt variables
# ====================================================================


class TestRule11PromptVariables:
    """Rule 11: prompt variables must be well-formed."""

    def test_valid_variables(self) -> None:
        data = _minimal_prompt_contract()
        errors = _validator.validate(data)
        rule11 = [e for e in errors if "rule-11" in e]
        assert rule11 == []

    def test_duplicate_variable_name(self) -> None:
        data = _minimal_prompt_contract(
            variables=[
                {"name": "x", "type": "STRING", "required": True, "description": "desc"},
                {"name": "x", "type": "STRING", "required": True, "description": "desc"},
            ]
        )
        errors = _validator.validate(data)
        rule11 = [e for e in errors if "rule-11" in e]
        assert any("duplicate" in e.lower() for e in rule11)

    def test_invalid_variable_type(self) -> None:
        data = _minimal_prompt_contract(
            variables=[
                {"name": "x", "type": "INVALID_TYPE", "required": True, "description": "desc"},
            ]
        )
        errors = _validator.validate(data)
        rule11 = [e for e in errors if "rule-11" in e]
        assert len(rule11) > 0

    def test_default_on_required_variable(self) -> None:
        data = _minimal_prompt_contract(
            variables=[
                {
                    "name": "x",
                    "type": "STRING",
                    "required": True,
                    "default": "should_not_be_here",
                    "description": "desc",
                },
            ]
        )
        errors = _validator.validate(data)
        rule11 = [e for e in errors if "rule-11" in e]
        assert any("default" in e.lower() for e in rule11)

    def test_default_on_optional_variable_ok(self) -> None:
        data = _minimal_prompt_contract(
            variables=[
                {
                    "name": "x",
                    "type": "STRING",
                    "required": False,
                    "default": "hello",
                    "description": "desc",
                },
            ]
        )
        errors = _validator.validate(data)
        rule11 = [e for e in errors if "rule-11" in e]
        assert rule11 == []

    def test_missing_required_field(self) -> None:
        data = _minimal_prompt_contract(
            variables=[
                {"name": "x", "type": "STRING", "description": "desc"},
            ]
        )
        errors = _validator.validate(data)
        rule11 = [e for e in errors if "rule-11" in e]
        assert any("required" in e.lower() for e in rule11)

    def test_rule_only_applies_to_prompt(self) -> None:
        """Rule 11 should not fire for tool contracts."""
        data = _minimal_tool_contract()
        errors = _validator.validate(data)
        rule11 = [e for e in errors if "rule-11" in e]
        assert rule11 == []


# ====================================================================
# Rule 12: Workflow DAG
# ====================================================================


class TestRule12WorkflowDag:
    """Rule 12: workflow steps must form an acyclic DAG."""

    def test_valid_dag(self) -> None:
        data = _minimal_workflow_contract(
            steps=[
                {"id": "s1", "capability": "tool.execute.a", "params": {}},
                {"id": "s2", "capability": "tool.execute.b", "params": {}, "deps": ["s1"]},
            ],
            dependencies={"s2": ["s1"]},
        )
        errors = _validator.validate(data)
        rule12 = [e for e in errors if "rule-12" in e]
        assert rule12 == []

    def test_cycle_detected(self) -> None:
        data = _minimal_workflow_contract(
            steps=[
                {"id": "s1", "capability": "tool.execute.a", "params": {}, "deps": ["s2"]},
                {"id": "s2", "capability": "tool.execute.b", "params": {}, "deps": ["s1"]},
            ],
            dependencies={"s1": ["s2"], "s2": ["s1"]},
        )
        errors = _validator.validate(data)
        rule12 = [e for e in errors if "rule-12" in e]
        assert any("cycle" in e.lower() for e in rule12)

    def test_dependency_references_nonexistent_step(self) -> None:
        data = _minimal_workflow_contract(
            steps=[
                {"id": "s1", "capability": "tool.execute.a", "params": {}, "deps": ["s99"]},
            ],
            dependencies={"s1": ["s99"]},
        )
        errors = _validator.validate(data)
        rule12 = [e for e in errors if "rule-12" in e]
        assert any("does not exist" in e.lower() for e in rule12)

    def test_duplicate_step_ids(self) -> None:
        data = _minimal_workflow_contract(
            steps=[
                {"id": "s1", "capability": "tool.execute.a", "params": {}},
                {"id": "s1", "capability": "tool.execute.b", "params": {}},
            ],
        )
        errors = _validator.validate(data)
        rule12 = [e for e in errors if "rule-12" in e]
        assert any("duplicate" in e.lower() for e in rule12)

    def test_rule_only_applies_to_workflow(self) -> None:
        """Rule 12 should not fire for tool contracts."""
        data = _minimal_tool_contract()
        errors = _validator.validate(data)
        rule12 = [e for e in errors if "rule-12" in e]
        assert rule12 == []


# ====================================================================
# Phase 1: JSON Schema structural validation
# ====================================================================


class TestPhase1JsonSchema:
    """JSON Schema Draft-07 structural violations caught in Phase 1."""

    def test_missing_root_key(self) -> None:
        errors = _validator.validate({"wrong_key": {}})
        assert len(errors) > 0

    def test_body_not_a_dict(self) -> None:
        errors = _validator.validate({"tool_contract": "not_a_dict"})
        assert len(errors) > 0

    def test_auto_detection_with_explicit_type(self) -> None:
        """Explicit contract_type overrides auto-detection."""
        data = _minimal_tool_contract()
        errors = _validator.validate(data, contract_type="tool_contract")
        assert errors == []


# ====================================================================
# Multiple errors accumulated
# ====================================================================


class TestMultipleErrors:
    """Validator accumulates all errors, not fail-fast."""

    def test_multiple_rule_violations(self) -> None:
        data = _minimal_tool_contract(
            name="INVALID",
            version="bad",
            domain=[],
            description="",
        )
        errors = _validator.validate(data)
        rule_ids = {e.split("]")[0].strip("[") for e in errors if e.startswith("[")}
        # Expect at least rules 1, 2, 3, 4 to fire
        assert "rule-01" in rule_ids or "schema" in str(errors)
        assert len(errors) >= 2, f"Expected multiple errors, got: {errors}"

    def test_error_object_attributes(self) -> None:
        data = _minimal_tool_contract(name="INVALID", version="bad")
        with pytest.raises(ContractValidationError) as exc_info:
            _validator.validate_or_raise(data)
        err = exc_info.value
        assert isinstance(err.errors, list)
        assert err.contract_type == "tool_contract"
        assert len(err.errors) >= 2
