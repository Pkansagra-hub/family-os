"""
Epic 6.4.5 -- test_agent_schema_validation.py -- Agent Contract Schema Validation.

Verifies the ContractValidator enforces all rules for agent_contract:

  Phase 1: JSON Schema (Draft-07) structural validation against
           agent_contract.schema.json.
  Phase 2: Semantic rules (rules 1-10 apply to agent contracts).

Covers:
  - Valid agent contract passes both phases.
  - Each of the 14 required fields triggers schema error when missing.
  - Name pattern violations (rule-01): agent.<verb>.<name>.
  - Semver violations (rule-02).
  - Domain violations (rule-03).
  - Description violations (rule-04).
  - Required inputs violations (rule-05).
  - Output schema violations (rule-06).
  - Provider type violations (rule-07): must be "AGENT".
  - Safety band violations (rule-08).
  - Availability violations (rule-09).
  - tools_granted pattern violations (rule-10).
  - Agent-specific fields: prompt_template, llm_budget_tokens,
    max_tool_calls, max_execution_time_ms.
  - validate_or_raise() raises ContractValidationError.
  - validate_body() convenience method.

References:
  - k1/contracts/schemas/agent_contract.schema.json
  - k1/fabric/core/contract_validator.py
  - fabric-implementation-plan.md Epic 6.4.5
"""

from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

from k1.fabric.core.contract_validator import (
    ContractValidationError,
    ContractValidator,
    detect_contract_type,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_AGENT_BODY: Dict[str, Any] = {
    "name": "agent.execute.health_advisor",
    "version": "1.0.0",
    "domain": ["HEALTH"],
    "description": "Provides health-related advice based on family context",
    "required_inputs": [
        {"name": "query", "type": "STRING", "description": "User health question"},
    ],
    "prompt_template": "health_advisor_v1",
    "tools_granted": [
        "tool.read.get_vitals",
        "tool.read.get_medications",
    ],
    "llm_budget_tokens": 4096,
    "max_tool_calls": 5,
    "max_execution_time_ms": 30000,
    "output": {"type": "object", "properties": {"answer": {"type": "string"}}},
    "provider_type": "AGENT",
    "safety_band_min": "GREEN",
    "availability": "ONLINE",
}


def _valid_agent() -> Dict[str, Any]:
    """Fresh deep copy of a valid agent contract (with root key)."""
    return {"agent_contract": copy.deepcopy(VALID_AGENT_BODY)}


@pytest.fixture
def validator() -> ContractValidator:
    return ContractValidator()


# ===================================================================
# 1. Happy path -- valid contract
# ===================================================================


class TestValidAgentContract:
    """A minimal valid agent contract must pass all validation rules."""

    def test_validate_returns_no_errors(self, validator: ContractValidator) -> None:
        errors = validator.validate(_valid_agent(), "agent_contract")
        assert errors == [], f"Unexpected errors: {errors}"

    def test_validate_or_raise_does_not_raise(self, validator: ContractValidator) -> None:
        validator.validate_or_raise(_valid_agent(), "agent_contract")

    def test_validate_body_returns_no_errors(self, validator: ContractValidator) -> None:
        errors = validator.validate_body(copy.deepcopy(VALID_AGENT_BODY), "agent_contract")
        assert errors == []

    def test_detect_contract_type(self) -> None:
        assert detect_contract_type(_valid_agent()) == "agent_contract"

    def test_auto_detect_without_explicit_type(self, validator: ContractValidator) -> None:
        errors = validator.validate(_valid_agent())
        assert errors == []


# ===================================================================
# 2. Required field missing -- JSON Schema errors
# ===================================================================


class TestAgentRequiredFieldsMissing:
    """Removing each required field must produce a schema error."""

    REQUIRED_FIELDS = [
        "name",
        "version",
        "domain",
        "description",
        "required_inputs",
        "prompt_template",
        "tools_granted",
        "llm_budget_tokens",
        "max_tool_calls",
        "max_execution_time_ms",
        "output",
        "provider_type",
        "safety_band_min",
        "availability",
    ]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_missing_field_produces_error(
        self, validator: ContractValidator, field: str
    ) -> None:
        data = _valid_agent()
        del data["agent_contract"][field]
        errors = validator.validate(data, "agent_contract")
        assert len(errors) > 0, f"Expected error for missing {field}"
        combined = " ".join(errors)
        assert field in combined or "required" in combined.lower()


# ===================================================================
# 3. Rule 01 -- name convention
# ===================================================================


class TestAgentNameConvention:
    """Validate FAB-11 name pattern: agent.<verb>.<name>."""

    @pytest.mark.parametrize(
        "name",
        [
            "agent.execute.health_advisor",
            "agent.spawn.finance_helper",
            "agent.execute.schedule_manager",
        ],
    )
    def test_valid_names(self, validator: ContractValidator, name: str) -> None:
        data = _valid_agent()
        data["agent_contract"]["name"] = name
        errors = validator.validate(data, "agent_contract")
        rule01 = [e for e in errors if "rule-01" in e]
        assert rule01 == [], f"Unexpected rule-01 errors for '{name}': {rule01}"

    @pytest.mark.parametrize(
        "name,reason",
        [
            ("execute.health_advisor", "missing agent. prefix"),
            ("agent.query.health_advisor", "invalid verb 'query'"),
            ("agent.execute", "missing name segment"),
            ("Agent.Execute.Health", "uppercase letters"),
            ("tool.execute.greeting", "wrong type prefix"),
            ("agent.execute.Health_Advisor", "uppercase in name"),
            ("", "empty name"),
            ("agent.read.x", "invalid verb 'read' for agent"),
        ],
    )
    def test_invalid_names(
        self, validator: ContractValidator, name: str, reason: str
    ) -> None:
        data = _valid_agent()
        data["agent_contract"]["name"] = name
        errors = validator.validate(data, "agent_contract")
        rule01 = [e for e in errors if "rule-01" in e]
        assert len(rule01) > 0, f"Expected rule-01 error for '{name}' ({reason})"


# ===================================================================
# 4. Rule 02 -- semver
# ===================================================================


class TestAgentSemver:
    """Validate version follows major.minor.patch."""

    @pytest.mark.parametrize("version", ["1.0.0", "0.1.0", "10.20.30"])
    def test_valid_versions(self, validator: ContractValidator, version: str) -> None:
        data = _valid_agent()
        data["agent_contract"]["version"] = version
        errors = validator.validate(data, "agent_contract")
        rule02 = [e for e in errors if "rule-02" in e]
        assert rule02 == []

    @pytest.mark.parametrize(
        "version",
        ["1.0", "v1.0.0", "1.0.0-beta", "abc", "1.0.0.0", ""],
    )
    def test_invalid_versions(self, validator: ContractValidator, version: str) -> None:
        data = _valid_agent()
        data["agent_contract"]["version"] = version
        errors = validator.validate(data, "agent_contract")
        rule02 = [e for e in errors if "rule-02" in e]
        assert len(rule02) > 0, f"Expected rule-02 error for '{version}'"


# ===================================================================
# 5. Rule 03 -- domain
# ===================================================================


class TestAgentDomain:
    """Validate domain has >= 1 non-empty tag."""

    def test_valid_single_domain(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        errors = validator.validate(data, "agent_contract")
        rule03 = [e for e in errors if "rule-03" in e]
        assert rule03 == []

    def test_empty_array(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["domain"] = []
        errors = validator.validate(data, "agent_contract")
        has_error = any("domain" in e.lower() or "rule-03" in e for e in errors)
        assert has_error

    def test_empty_string_tag(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["domain"] = [""]
        errors = validator.validate(data, "agent_contract")
        has_error = any("domain" in e.lower() or "rule-03" in e or "minLength" in e for e in errors)
        assert has_error


# ===================================================================
# 6. Rule 04 -- description
# ===================================================================


class TestAgentDescription:
    """Validate description non-empty and <= 512 chars."""

    def test_empty_description(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["description"] = ""
        errors = validator.validate(data, "agent_contract")
        has_error = any("rule-04" in e or "description" in e.lower() for e in errors)
        assert has_error

    def test_too_long_description(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["description"] = "x" * 513
        errors = validator.validate(data, "agent_contract")
        has_error = any("rule-04" in e or "maxLength" in e or "512" in e for e in errors)
        assert has_error


# ===================================================================
# 7. Rule 05 -- required_inputs
# ===================================================================


class TestAgentRequiredInputs:
    """Validate required_inputs items have name, type, description."""

    @pytest.mark.parametrize("missing_field", ["name", "type", "description"])
    def test_input_missing_field(
        self, validator: ContractValidator, missing_field: str
    ) -> None:
        data = _valid_agent()
        inp = {"name": "q", "type": "STRING", "description": "Q"}
        del inp[missing_field]
        data["agent_contract"]["required_inputs"] = [inp]
        errors = validator.validate(data, "agent_contract")
        has_error = any("rule-05" in e or missing_field in e for e in errors)
        assert has_error


# ===================================================================
# 8. Rule 06 -- output schema
# ===================================================================


class TestAgentOutputSchema:
    """Validate output has 'type' property for agent contracts."""

    def test_valid_output(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        errors = validator.validate(data, "agent_contract")
        rule06 = [e for e in errors if "rule-06" in e]
        assert rule06 == []

    def test_output_missing_type(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["output"] = {"properties": {}}
        errors = validator.validate(data, "agent_contract")
        has_error = any("rule-06" in e or "type" in e for e in errors)
        assert has_error


# ===================================================================
# 9. Rule 07 -- provider_type (agent-specific)
# ===================================================================


class TestAgentProviderType:
    """Agent contracts must have provider_type="AGENT"."""

    def test_agent_provider_type_valid(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        errors = validator.validate(data, "agent_contract")
        rule07 = [e for e in errors if "rule-07" in e]
        assert rule07 == []

    @pytest.mark.parametrize("pt", ["MCP", "WASM", "BRIDGE", "WORKFLOW"])
    def test_non_agent_provider_type_rejected(
        self, validator: ContractValidator, pt: str
    ) -> None:
        data = _valid_agent()
        data["agent_contract"]["provider_type"] = pt
        errors = validator.validate(data, "agent_contract")
        has_error = any("rule-07" in e or "provider_type" in e for e in errors)
        assert has_error, f"Expected error for provider_type={pt}"

    def test_invalid_provider_type(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["provider_type"] = "UNKNOWN"
        errors = validator.validate(data, "agent_contract")
        has_error = any("rule-07" in e or "provider_type" in e for e in errors)
        assert has_error


# ===================================================================
# 10. Rule 08 -- safety_band_min
# ===================================================================


class TestAgentSafetyBand:
    """Validate safety_band_min enum."""

    @pytest.mark.parametrize("band", ["GREEN", "AMBER", "RED", "CRISIS"])
    def test_valid_bands(self, validator: ContractValidator, band: str) -> None:
        data = _valid_agent()
        data["agent_contract"]["safety_band_min"] = band
        errors = validator.validate(data, "agent_contract")
        rule08 = [e for e in errors if "rule-08" in e]
        assert rule08 == []

    def test_invalid_band(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["safety_band_min"] = "YELLOW"
        errors = validator.validate(data, "agent_contract")
        has_error = any("rule-08" in e or "safety_band" in e for e in errors)
        assert has_error


# ===================================================================
# 11. Rule 09 -- availability
# ===================================================================


class TestAgentAvailability:
    """Validate availability enum."""

    @pytest.mark.parametrize("avail", ["ONLINE", "DEGRADED", "OFFLINE"])
    def test_valid_availability(self, validator: ContractValidator, avail: str) -> None:
        data = _valid_agent()
        data["agent_contract"]["availability"] = avail
        errors = validator.validate(data, "agent_contract")
        rule09 = [e for e in errors if "rule-09" in e]
        assert rule09 == []

    def test_invalid_availability(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["availability"] = "DOWN"
        errors = validator.validate(data, "agent_contract")
        has_error = any("rule-09" in e or "availability" in e for e in errors)
        assert has_error


# ===================================================================
# 12. Rule 10 -- tools_granted pattern validation
# ===================================================================


class TestAgentToolsGranted:
    """Validate tools_granted references follow tool naming convention."""

    def test_valid_tools_granted(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        errors = validator.validate(data, "agent_contract")
        rule10 = [e for e in errors if "rule-10" in e]
        assert rule10 == []

    def test_empty_tools_granted_ok(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["tools_granted"] = []
        errors = validator.validate(data, "agent_contract")
        rule10 = [e for e in errors if "rule-10" in e]
        assert rule10 == []

    @pytest.mark.parametrize(
        "tool_ref",
        [
            "tool.execute.send_message",
            "tool.read.get_vitals",
            "tool.write.save_note",
            "tool.delete.remove_entry",
            # Multi-segment IFL/MCP
            "tool.execute.home.hue.set_brightness",
            "tool.execute.mcp.get_weather",
        ],
    )
    def test_valid_tool_references(
        self, validator: ContractValidator, tool_ref: str
    ) -> None:
        data = _valid_agent()
        data["agent_contract"]["tools_granted"] = [tool_ref]
        errors = validator.validate(data, "agent_contract")
        rule10 = [e for e in errors if "rule-10" in e]
        assert rule10 == [], f"Unexpected rule-10 error for {tool_ref}"

    @pytest.mark.parametrize(
        "tool_ref,reason",
        [
            ("invalid_tool_name", "no prefix"),
            ("TOOL.EXECUTE.UPPER", "uppercase"),
            ("tool.query.something", "invalid verb"),
            ("tool.execute", "missing name"),
            ("", "empty string"),
        ],
    )
    def test_invalid_tool_references(
        self, validator: ContractValidator, tool_ref: str, reason: str
    ) -> None:
        data = _valid_agent()
        data["agent_contract"]["tools_granted"] = [tool_ref]
        errors = validator.validate(data, "agent_contract")
        has_error = any("rule-10" in e or "tools_granted" in e for e in errors)
        assert has_error, f"Expected error for tool_ref '{tool_ref}' ({reason})"


# ===================================================================
# 13. Agent-specific fields -- prompt_template
# ===================================================================


class TestAgentPromptTemplate:
    """Validate prompt_template is required and non-empty."""

    def test_valid_prompt_template(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        errors = validator.validate(data, "agent_contract")
        assert errors == []

    def test_empty_prompt_template(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["prompt_template"] = ""
        errors = validator.validate(data, "agent_contract")
        has_error = any("prompt_template" in e or "minLength" in e for e in errors)
        assert has_error


# ===================================================================
# 14. Agent-specific fields -- llm_budget_tokens
# ===================================================================


class TestAgentLlmBudgetTokens:
    """Validate llm_budget_tokens is integer >= 1."""

    def test_valid_budget(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["llm_budget_tokens"] = 1
        errors = validator.validate(data, "agent_contract")
        budget_errors = [e for e in errors if "llm_budget" in e or "minimum" in e]
        assert budget_errors == []

    def test_zero_budget_rejected(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["llm_budget_tokens"] = 0
        errors = validator.validate(data, "agent_contract")
        has_error = any("llm_budget" in e or "minimum" in e for e in errors)
        assert has_error

    def test_negative_budget_rejected(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["llm_budget_tokens"] = -1
        errors = validator.validate(data, "agent_contract")
        has_error = any("llm_budget" in e or "minimum" in e for e in errors)
        assert has_error


# ===================================================================
# 15. Agent-specific fields -- max_tool_calls
# ===================================================================


class TestAgentMaxToolCalls:
    """Validate max_tool_calls is integer >= 0."""

    def test_zero_tool_calls_ok(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["max_tool_calls"] = 0
        errors = validator.validate(data, "agent_contract")
        tool_errors = [e for e in errors if "max_tool_calls" in e or "minimum" in e]
        assert tool_errors == []

    def test_positive_tool_calls_ok(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["max_tool_calls"] = 10
        errors = validator.validate(data, "agent_contract")
        tool_errors = [e for e in errors if "max_tool_calls" in e]
        assert tool_errors == []

    def test_negative_tool_calls_rejected(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["max_tool_calls"] = -1
        errors = validator.validate(data, "agent_contract")
        has_error = any("max_tool_calls" in e or "minimum" in e for e in errors)
        assert has_error


# ===================================================================
# 16. Agent-specific fields -- max_execution_time_ms
# ===================================================================


class TestAgentMaxExecutionTime:
    """Validate max_execution_time_ms is integer >= 1."""

    def test_valid_execution_time(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        errors = validator.validate(data, "agent_contract")
        time_errors = [e for e in errors if "max_execution" in e]
        assert time_errors == []

    def test_minimum_execution_time(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["max_execution_time_ms"] = 1
        errors = validator.validate(data, "agent_contract")
        time_errors = [e for e in errors if "max_execution" in e or "minimum" in e]
        assert time_errors == []

    def test_zero_execution_time_rejected(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["max_execution_time_ms"] = 0
        errors = validator.validate(data, "agent_contract")
        has_error = any("max_execution" in e or "minimum" in e for e in errors)
        assert has_error


# ===================================================================
# 17. ContractValidationError exception
# ===================================================================


class TestAgentValidationError:
    """Verify ContractValidationError has correct attributes."""

    def test_error_raised_with_details(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["name"] = "INVALID"
        data["agent_contract"]["version"] = "bad"
        with pytest.raises(ContractValidationError) as exc_info:
            validator.validate_or_raise(data, "agent_contract")
        err = exc_info.value
        assert err.contract_type == "agent_contract"
        assert len(err.errors) >= 2

    def test_error_string_contains_type(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        del data["agent_contract"]["name"]
        with pytest.raises(ContractValidationError) as exc_info:
            validator.validate_or_raise(data, "agent_contract")
        assert "agent_contract" in str(exc_info.value)


# ===================================================================
# 18. Optional fields -- valid contract with optional fields
# ===================================================================


class TestAgentOptionalFields:
    """Optional fields should not cause errors when present and valid."""

    def test_with_optional_fields(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"].update(
            {
                "capabilities": ["advise", "recommend"],
                "limitations": ["cannot prescribe medication"],
                "optional_inputs": [
                    {"name": "language", "type": "STRING", "description": "Language preference"}
                ],
                "required_context": ["beliefs_active.entities"],
                "optional_context": ["persona.name"],
                "template_file": "k1/contracts/agents/health_advisor.yaml",
                "provider_id": "health-agent-01",
                "provider_endpoint": "agent://local/health_advisor",
                "cost_per_call": 0.01,
                "avg_latency_ms": 500,
                "max_latency_ms": 5000,
            }
        )
        errors = validator.validate(data, "agent_contract")
        assert errors == [], f"Unexpected errors with optional fields: {errors}"

    def test_with_metrics_fields(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["registered_at"] = "2025-01-01T00:00:00Z"
        data["agent_contract"]["last_updated"] = "2025-06-01T12:00:00Z"
        data["agent_contract"]["success_rate_30d"] = 0.92
        data["agent_contract"]["total_invocations_30d"] = 500
        errors = validator.validate(data, "agent_contract")
        assert errors == []


# ===================================================================
# 19. Schema-level constraints
# ===================================================================


class TestAgentSchemaConstraints:
    """Test JSON Schema constraints beyond required fields."""

    def test_additional_properties_rejected(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["unknown_field"] = "surprise"
        errors = validator.validate(data, "agent_contract")
        has_error = any("additional" in e.lower() for e in errors)
        assert has_error

    def test_additional_properties_at_root_rejected(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["extra_key"] = "should fail"
        errors = validator.validate(data, "agent_contract")
        has_error = any("additional" in e.lower() for e in errors)
        assert has_error

    def test_domain_unique_items(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["domain"] = ["HEALTH", "HEALTH"]
        errors = validator.validate(data, "agent_contract")
        has_error = any("unique" in e.lower() for e in errors)
        assert has_error

    def test_success_rate_out_of_range(self, validator: ContractValidator) -> None:
        data = _valid_agent()
        data["agent_contract"]["success_rate_30d"] = 1.5
        errors = validator.validate(data, "agent_contract")
        has_error = any("success_rate" in e or "maximum" in e for e in errors)
        assert has_error

    def test_tools_granted_schema_pattern(self, validator: ContractValidator) -> None:
        """JSON Schema pattern on tools_granted items catches bad patterns."""
        data = _valid_agent()
        data["agent_contract"]["tools_granted"] = ["INVALID"]
        errors = validator.validate(data, "agent_contract")
        assert len(errors) > 0
