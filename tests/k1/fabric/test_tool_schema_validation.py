"""
Epic 6.4.4 -- test_tool_schema_validation.py -- Tool Contract Schema Validation.

Verifies the ContractValidator enforces all rules for tool_contract:

  Phase 1: JSON Schema (Draft-07) structural validation against
           tool_contract.schema.json.
  Phase 2: 12 semantic rules from fabric_discussion.md Section 6.
           Rules 10-12 are N/A for tool contracts (agent/prompt/workflow only).

Covers:
  - Valid tool contract passes both phases.
  - Each of the 10 required fields triggers schema error when missing.
  - Name pattern violations (rule-01).
  - Semver violations (rule-02).
  - Domain violations (rule-03).
  - Description violations (rule-04).
  - Required inputs violations (rule-05).
  - Output schema violations (rule-06).
  - Provider type violations (rule-07).
  - Safety band violations (rule-08).
  - Availability violations (rule-09).
  - validate_or_raise() raises ContractValidationError.
  - validate_body() convenience method.
  - detect_contract_type() auto-detection.

References:
  - k1/contracts/schemas/tool_contract.schema.json
  - k1/fabric/core/contract_validator.py
  - fabric-implementation-plan.md Epic 6.4.4
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

VALID_TOOL_BODY: Dict[str, Any] = {
    "name": "tool.execute.send_message",
    "version": "1.0.0",
    "domain": ["SOCIAL"],
    "description": "Send a message to a family member",
    "required_inputs": [
        {"name": "recipient", "type": "STRING", "description": "Recipient name"},
        {"name": "message", "type": "STRING", "description": "Message body"},
    ],
    "output": {"type": "object", "properties": {"status": {"type": "string"}}},
    "provider_type": "MCP",
    "provider_id": "mcp-local-messaging",
    "safety_band_min": "GREEN",
    "availability": "ONLINE",
}


def _valid_tool() -> Dict[str, Any]:
    """Fresh deep copy of a valid tool contract (with root key)."""
    return {"tool_contract": copy.deepcopy(VALID_TOOL_BODY)}


@pytest.fixture
def validator() -> ContractValidator:
    return ContractValidator()


# ===================================================================
# 1. Happy path -- valid contract
# ===================================================================


class TestValidToolContract:
    """A minimal valid tool contract must pass all validation rules."""

    def test_validate_returns_no_errors(self, validator: ContractValidator) -> None:
        errors = validator.validate(_valid_tool(), "tool_contract")
        assert errors == [], f"Unexpected errors: {errors}"

    def test_validate_or_raise_does_not_raise(self, validator: ContractValidator) -> None:
        validator.validate_or_raise(_valid_tool(), "tool_contract")

    def test_validate_body_returns_no_errors(self, validator: ContractValidator) -> None:
        errors = validator.validate_body(copy.deepcopy(VALID_TOOL_BODY), "tool_contract")
        assert errors == []

    def test_detect_contract_type(self) -> None:
        assert detect_contract_type(_valid_tool()) == "tool_contract"

    def test_auto_detect_without_explicit_type(self, validator: ContractValidator) -> None:
        errors = validator.validate(_valid_tool())
        assert errors == []


# ===================================================================
# 2. Required field missing -- JSON Schema errors
# ===================================================================


class TestToolRequiredFieldsMissing:
    """Removing each required field must produce a schema error."""

    REQUIRED_FIELDS = [
        "name",
        "version",
        "domain",
        "description",
        "required_inputs",
        "output",
        "provider_type",
        "provider_id",
        "safety_band_min",
        "availability",
    ]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_missing_field_produces_error(
        self, validator: ContractValidator, field: str
    ) -> None:
        data = _valid_tool()
        del data["tool_contract"][field]
        errors = validator.validate(data, "tool_contract")
        assert len(errors) > 0, f"Expected error for missing {field}"
        # At least one error should reference the field name
        combined = " ".join(errors)
        assert field in combined or "required" in combined.lower()


# ===================================================================
# 3. Rule 01 -- name convention
# ===================================================================


class TestToolNameConvention:
    """Validate FAB-11 name pattern: tool.<verb>.<name>."""

    @pytest.mark.parametrize(
        "name",
        [
            "tool.execute.send_message",
            "tool.read.get_weather",
            "tool.write.save_note",
            "tool.delete.remove_entry",
            # Multi-segment (IFL/MCP) -- allowed by code pattern
            "tool.execute.home.hue.set_brightness",
            "tool.execute.mcp.get_weather",
        ],
    )
    def test_valid_names(self, validator: ContractValidator, name: str) -> None:
        data = _valid_tool()
        data["tool_contract"]["name"] = name
        errors = validator.validate(data, "tool_contract")
        rule01 = [e for e in errors if "rule-01" in e]
        assert rule01 == [], f"Unexpected rule-01 errors for '{name}': {rule01}"

    @pytest.mark.parametrize(
        "name,reason",
        [
            ("execute.send_message", "missing tool. prefix"),
            ("tool.query.send_message", "invalid verb 'query'"),
            ("tool.execute", "missing name segment"),
            ("Tool.Execute.Send", "uppercase letters"),
            ("agent.execute.greeting", "wrong type prefix"),
            ("tool.execute.Send_Message", "uppercase in name"),
            ("", "empty name"),
        ],
    )
    def test_invalid_names(
        self, validator: ContractValidator, name: str, reason: str
    ) -> None:
        data = _valid_tool()
        data["tool_contract"]["name"] = name
        errors = validator.validate(data, "tool_contract")
        rule01 = [e for e in errors if "rule-01" in e]
        assert len(rule01) > 0, f"Expected rule-01 error for '{name}' ({reason})"


# ===================================================================
# 4. Rule 02 -- semver
# ===================================================================


class TestToolSemver:
    """Validate version follows major.minor.patch."""

    @pytest.mark.parametrize("version", ["1.0.0", "0.1.0", "10.20.30"])
    def test_valid_versions(self, validator: ContractValidator, version: str) -> None:
        data = _valid_tool()
        data["tool_contract"]["version"] = version
        errors = validator.validate(data, "tool_contract")
        rule02 = [e for e in errors if "rule-02" in e]
        assert rule02 == []

    @pytest.mark.parametrize(
        "version",
        ["1.0", "v1.0.0", "1.0.0-beta", "abc", "1.0.0.0", ""],
    )
    def test_invalid_versions(self, validator: ContractValidator, version: str) -> None:
        data = _valid_tool()
        data["tool_contract"]["version"] = version
        errors = validator.validate(data, "tool_contract")
        rule02 = [e for e in errors if "rule-02" in e]
        assert len(rule02) > 0, f"Expected rule-02 error for '{version}'"


# ===================================================================
# 5. Rule 03 -- domain
# ===================================================================


class TestToolDomain:
    """Validate domain has >= 1 non-empty tag."""

    def test_valid_single_domain(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["domain"] = ["HEALTH"]
        errors = validator.validate(data, "tool_contract")
        rule03 = [e for e in errors if "rule-03" in e]
        assert rule03 == []

    def test_valid_multi_domain(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["domain"] = ["HEALTH", "FOOD"]
        errors = validator.validate(data, "tool_contract")
        rule03 = [e for e in errors if "rule-03" in e]
        assert rule03 == []

    def test_empty_array(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["domain"] = []
        errors = validator.validate(data, "tool_contract")
        has_domain_error = any("domain" in e.lower() or "rule-03" in e for e in errors)
        assert has_domain_error

    def test_empty_string_tag(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["domain"] = [""]
        errors = validator.validate(data, "tool_contract")
        has_error = any("domain" in e.lower() or "rule-03" in e or "minLength" in e for e in errors)
        assert has_error


# ===================================================================
# 6. Rule 04 -- description
# ===================================================================


class TestToolDescription:
    """Validate description non-empty and <= 512 chars."""

    def test_valid_description(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        errors = validator.validate(data, "tool_contract")
        rule04 = [e for e in errors if "rule-04" in e]
        assert rule04 == []

    def test_empty_description(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["description"] = ""
        errors = validator.validate(data, "tool_contract")
        has_error = any("rule-04" in e or "description" in e.lower() for e in errors)
        assert has_error

    def test_too_long_description(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["description"] = "x" * 513
        errors = validator.validate(data, "tool_contract")
        has_error = any("rule-04" in e or "maxLength" in e or "512" in e for e in errors)
        assert has_error

    def test_max_length_description_ok(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["description"] = "x" * 512
        errors = validator.validate(data, "tool_contract")
        rule04 = [e for e in errors if "rule-04" in e]
        assert rule04 == []


# ===================================================================
# 7. Rule 05 -- required_inputs
# ===================================================================


class TestToolRequiredInputs:
    """Validate required_inputs items have name, type, description."""

    def test_valid_inputs(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        errors = validator.validate(data, "tool_contract")
        rule05 = [e for e in errors if "rule-05" in e]
        assert rule05 == []

    def test_empty_inputs_ok(self, validator: ContractValidator) -> None:
        """Empty required_inputs array is allowed."""
        data = _valid_tool()
        data["tool_contract"]["required_inputs"] = []
        errors = validator.validate(data, "tool_contract")
        rule05 = [e for e in errors if "rule-05" in e]
        assert rule05 == []

    @pytest.mark.parametrize("missing_field", ["name", "type", "description"])
    def test_input_missing_field(
        self, validator: ContractValidator, missing_field: str
    ) -> None:
        data = _valid_tool()
        inp = {"name": "x", "type": "STRING", "description": "X"}
        del inp[missing_field]
        data["tool_contract"]["required_inputs"] = [inp]
        errors = validator.validate(data, "tool_contract")
        has_error = any("rule-05" in e or missing_field in e for e in errors)
        assert has_error, f"Expected error for missing {missing_field}"


# ===================================================================
# 8. Rule 06 -- output schema
# ===================================================================


class TestToolOutputSchema:
    """Validate output has 'type' property."""

    def test_valid_output(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        errors = validator.validate(data, "tool_contract")
        rule06 = [e for e in errors if "rule-06" in e]
        assert rule06 == []

    def test_output_missing_type(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["output"] = {"properties": {}}
        errors = validator.validate(data, "tool_contract")
        has_error = any("rule-06" in e or "type" in e for e in errors)
        assert has_error

    def test_output_string_type(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["output"] = {"type": "string"}
        errors = validator.validate(data, "tool_contract")
        rule06 = [e for e in errors if "rule-06" in e]
        assert rule06 == []


# ===================================================================
# 9. Rule 07 -- provider_type (tool-specific)
# ===================================================================


class TestToolProviderType:
    """Tool contracts allow MCP, WASM, BRIDGE only."""

    @pytest.mark.parametrize("pt", ["MCP", "WASM", "BRIDGE"])
    def test_valid_provider_types(self, validator: ContractValidator, pt: str) -> None:
        data = _valid_tool()
        data["tool_contract"]["provider_type"] = pt
        errors = validator.validate(data, "tool_contract")
        rule07 = [e for e in errors if "rule-07" in e]
        assert rule07 == [], f"Unexpected rule-07 error for {pt}"

    def test_agent_rejected_for_tool(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["provider_type"] = "AGENT"
        errors = validator.validate(data, "tool_contract")
        rule07 = [e for e in errors if "rule-07" in e]
        assert len(rule07) > 0

    def test_workflow_rejected_for_tool(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["provider_type"] = "WORKFLOW"
        errors = validator.validate(data, "tool_contract")
        # Schema error (enum) and/or rule-07
        has_error = any("rule-07" in e or "provider_type" in e for e in errors)
        assert has_error

    def test_invalid_provider_type(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["provider_type"] = "UNKNOWN"
        errors = validator.validate(data, "tool_contract")
        has_error = any("rule-07" in e or "provider_type" in e for e in errors)
        assert has_error


# ===================================================================
# 10. Rule 08 -- safety_band_min
# ===================================================================


class TestToolSafetyBand:
    """Validate safety_band_min enum."""

    @pytest.mark.parametrize("band", ["GREEN", "AMBER", "RED", "CRISIS"])
    def test_valid_bands(self, validator: ContractValidator, band: str) -> None:
        data = _valid_tool()
        data["tool_contract"]["safety_band_min"] = band
        errors = validator.validate(data, "tool_contract")
        rule08 = [e for e in errors if "rule-08" in e]
        assert rule08 == []

    def test_invalid_band(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["safety_band_min"] = "YELLOW"
        errors = validator.validate(data, "tool_contract")
        has_error = any("rule-08" in e or "safety_band" in e for e in errors)
        assert has_error


# ===================================================================
# 11. Rule 09 -- availability
# ===================================================================


class TestToolAvailability:
    """Validate availability enum."""

    @pytest.mark.parametrize("avail", ["ONLINE", "DEGRADED", "OFFLINE"])
    def test_valid_availability(self, validator: ContractValidator, avail: str) -> None:
        data = _valid_tool()
        data["tool_contract"]["availability"] = avail
        errors = validator.validate(data, "tool_contract")
        rule09 = [e for e in errors if "rule-09" in e]
        assert rule09 == []

    def test_invalid_availability(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["availability"] = "DOWN"
        errors = validator.validate(data, "tool_contract")
        has_error = any("rule-09" in e or "availability" in e for e in errors)
        assert has_error


# ===================================================================
# 12. ContractValidationError exception
# ===================================================================


class TestToolValidationError:
    """Verify ContractValidationError has correct attributes."""

    def test_error_raised_with_details(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["name"] = "INVALID"
        data["tool_contract"]["version"] = "bad"
        with pytest.raises(ContractValidationError) as exc_info:
            validator.validate_or_raise(data, "tool_contract")
        err = exc_info.value
        assert err.contract_type == "tool_contract"
        assert len(err.errors) >= 2  # At least schema + rule errors

    def test_error_string_contains_summary(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        del data["tool_contract"]["name"]
        with pytest.raises(ContractValidationError) as exc_info:
            validator.validate_or_raise(data, "tool_contract")
        assert "tool_contract" in str(exc_info.value)


# ===================================================================
# 13. Optional fields -- valid contract with optional fields
# ===================================================================


class TestToolOptionalFields:
    """Optional fields should not cause errors when present and valid."""

    def test_with_all_optional_fields(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"].update(
            {
                "capabilities": ["send", "receive"],
                "limitations": ["no attachments"],
                "optional_inputs": [
                    {"name": "priority", "type": "STRING", "description": "Priority level"}
                ],
                "required_context": ["beliefs_active.entities"],
                "optional_context": ["persona.name"],
                "provider_endpoint": "mcp://local/messaging",
                "cost_per_call": 0.001,
                "avg_latency_ms": 50,
                "max_latency_ms": 200,
                "tags": ["social", "messaging"],
            }
        )
        errors = validator.validate(data, "tool_contract")
        assert errors == [], f"Unexpected errors with optional fields: {errors}"

    def test_with_registered_at_and_last_updated(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["registered_at"] = "2025-01-01T00:00:00Z"
        data["tool_contract"]["last_updated"] = "2025-06-01T12:00:00Z"
        errors = validator.validate(data, "tool_contract")
        assert errors == []

    def test_with_success_rate(self, validator: ContractValidator) -> None:
        data = _valid_tool()
        data["tool_contract"]["success_rate_30d"] = 0.95
        data["tool_contract"]["total_invocations_30d"] = 1000
        errors = validator.validate(data, "tool_contract")
        assert errors == []


# ===================================================================
# 14. Schema-level constraints
# ===================================================================


class TestToolSchemaConstraints:
    """Test JSON Schema constraints beyond required fields."""

    def test_additional_properties_rejected(self, validator: ContractValidator) -> None:
        """additionalProperties=false at tool_contract level."""
        data = _valid_tool()
        data["tool_contract"]["unknown_field"] = "surprise"
        errors = validator.validate(data, "tool_contract")
        has_error = any("additional" in e.lower() for e in errors)
        assert has_error

    def test_additional_properties_at_root_rejected(self, validator: ContractValidator) -> None:
        """additionalProperties=false at root level."""
        data = _valid_tool()
        data["extra_key"] = "should fail"
        errors = validator.validate(data, "tool_contract")
        has_error = any("additional" in e.lower() for e in errors)
        assert has_error

    def test_domain_unique_items(self, validator: ContractValidator) -> None:
        """domain must have uniqueItems=true."""
        data = _valid_tool()
        data["tool_contract"]["domain"] = ["HEALTH", "HEALTH"]
        errors = validator.validate(data, "tool_contract")
        has_error = any("unique" in e.lower() for e in errors)
        assert has_error

    def test_input_spec_additional_properties_rejected(self, validator: ContractValidator) -> None:
        """input_spec has additionalProperties=false."""
        data = _valid_tool()
        data["tool_contract"]["required_inputs"] = [
            {
                "name": "x",
                "type": "STRING",
                "description": "X",
                "unexpected": True,
            }
        ]
        errors = validator.validate(data, "tool_contract")
        has_error = any("additional" in e.lower() for e in errors)
        assert has_error
