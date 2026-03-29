"""
Epic 6.3.13 -- Test output validation end-to-end (integration).

Full output validation pipeline through Fabric public API:
  register contract with output schema -> inject custom MCPResponse ->
  fabric.execute() -> verify validation pass/reject -> verify events.

3-tier validation pipeline tested:
  - Tier 1: Structural (required fields, data is dict, truncation, size)
  - Tier 2: Schema (JSON Schema match against contract.output)
  - Tier 3: Semantic (soft-fail only, agent providers)

MANDATORY per plan:
  1. ALL mutations/reads through fabric.execute() -- NEVER direct pipeline access.
  2. Uses FabricFactory.create_for_testing() with event capture.
  3. Real adapters only (test adapters are real, not mocks).
  4. Custom MCPResponse injected via TestMCPTransport.add_response().
  5. No mocks anywhere.

References:
  - fabric-implementation-plan.md Epic 6.3, Issue 6.3.13
  - No-Mock Testing Strategy (lines 1181-1300 of plan)
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from k1.fabric.adapters.test_mcp_transport import TestMCPTransport
from k1.fabric.events.fabric_events import (
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_LEARNING_SIGNAL,
)
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory
from k1.fabric.output_validation.structural_validator import DEFAULT_MAX_DATA_BYTES
from k1.fabric.output_validation.validation_fallback import EVENT_VALIDATION_FAILED
from k1.fabric.providers.mcp_provider import MCPResponse
from k1.fabric.types import (
    Availability,
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    SafetyBand,
    Tier,
)
from tests.k1.fabric.helpers import (
    assert_capability_result_failure,
    assert_capability_result_success,
    register_contract_with_provider,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_transport() -> TestMCPTransport:
    """Create a TestMCPTransport instance."""
    return TestMCPTransport(connected=True)


def _make_fabric(transport: TestMCPTransport) -> Fabric:
    """Create a Fabric with custom MCP transport and event capture."""
    return FabricFactory.create_for_testing(
        capture_events=True,
        mcp_transport=transport,
    )


def _make_request(
    capability_name: str,
    params: dict | None = None,
) -> CapabilityRequest:
    """Build a LOW tier CapabilityRequest."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params or {},
        tier=Tier.LOW.value,
        caller="test-output-validation",
    )


def _make_contract(
    name: str = "tool.execute.ov_test",
    output_schema: Dict[str, Any] | None = None,
    provider_id: str = "ov-mcp-provider",
) -> CapabilityContract:
    """Create a contract with custom output schema."""
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["test"],
        description="Output validation test capability",
        capabilities=["test"],
        limitations=[],
        required_inputs=[
            InputSpec(name="query", type="STRING", description="Test input"),
        ],
        output=output_schema or {"type": "object"},
        provider_type="MCP",
        provider_id=provider_id,
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
    )


def _json_response(data: Dict[str, Any]) -> MCPResponse:
    """Create MCPResponse with JSON text content."""
    return MCPResponse(
        success=True,
        content=[{"type": "text", "text": json.dumps(data)}],
        latency_ms=1,
    )


def _text_response(text: str) -> MCPResponse:
    """Create MCPResponse with plain text content."""
    return MCPResponse(
        success=True,
        content=[{"type": "text", "text": text}],
        latency_ms=1,
    )


# =========================================================================
# 6.3.13a -- Valid output passes through (Tier 1+2 pass)
# =========================================================================


class TestValidOutputPassesThrough:
    """Verify that valid provider outputs pass all validation tiers."""

    @pytest.mark.asyncio
    async def test_valid_dict_output_succeeds(self) -> None:
        """Provider returns valid JSON dict that matches contract.output schema."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_valid_dict",
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                },
                "required": ["status"],
            },
            provider_id="ov-valid-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Inject a valid response matching the schema
        transport.add_response(
            "tool.execute.ov_valid_dict",
            _json_response({"status": "ok"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_valid_dict"))

        assert_capability_result_success(result, expected_provider="ov-valid-provider")
        assert result.data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_valid_output_emits_completed_event(self) -> None:
        """On valid output, completed event is emitted (not validation failed)."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_completed_evt",
            provider_id="ov-evt-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Default response returns {"result": "test response"} which passes {"type": "object"}
        result = await fabric.execute(_make_request("tool.execute.ov_completed_evt"))
        assert_capability_result_success(result)

        # Should emit completed, NOT validation failed
        completed = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_COMPLETED)
        assert len(completed) >= 1

        validation_failed = fabric.event_port.get_captured(topic=EVENT_VALIDATION_FAILED)
        assert len(validation_failed) == 0

    @pytest.mark.asyncio
    async def test_valid_output_with_extra_fields_passes_permissive_schema(self) -> None:
        """Extra fields pass when additionalProperties is not restricted."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_extra_fields",
            output_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
            provider_id="ov-extra-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_extra_fields",
            _json_response({"name": "test", "extra_field": 42}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_extra_fields"))
        assert_capability_result_success(result)
        assert result.data["name"] == "test"
        assert result.data["extra_field"] == 42

    @pytest.mark.asyncio
    async def test_permissive_output_schema_passes_any_dict(self) -> None:
        """Contract with permissive output schema {type: object} passes any dict."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_permissive",
            output_schema={"type": "object"},
            provider_id="ov-permissive-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Any valid dict response passes the permissive schema
        transport.add_response(
            "tool.execute.ov_permissive",
            _json_response({"arbitrary": "data", "count": 42, "nested": {"a": 1}}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_permissive"))
        assert_capability_result_success(result)
        assert result.data["arbitrary"] == "data"

    @pytest.mark.asyncio
    async def test_learning_signal_emitted_on_valid_output(self) -> None:
        """Learning signal is emitted after successful validation."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_learning_ok",
            provider_id="ov-learning-provider",
        )
        register_contract_with_provider(fabric, contract)

        result = await fabric.execute(_make_request("tool.execute.ov_learning_ok"))
        assert_capability_result_success(result)

        signals = fabric.event_port.get_captured(topic=TOPIC_LEARNING_SIGNAL)
        assert len(signals) >= 1
        _, payload = signals[0]
        assert payload["capability_name"] == "tool.execute.ov_learning_ok"
        assert payload["success"] is True


# =========================================================================
# 6.3.13b -- Structural validation rejects malformed output
# =========================================================================


class TestStructuralValidationRejects:
    """Verify that Tier 1 (structural) failures cause execution rejection."""

    @pytest.mark.asyncio
    async def test_truncation_markers_rejected(self) -> None:
        """Output containing truncation markers is rejected at structural tier."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_trunc",
            provider_id="ov-trunc-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Inject response with truncation marker
        transport.add_response(
            "tool.execute.ov_trunc",
            _json_response({"data": "Hello [truncated]"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_trunc"))

        assert_capability_result_failure(result, error_code="output_validation_failed")

    @pytest.mark.asyncio
    async def test_truncation_emits_validation_failed_event(self) -> None:
        """Structural rejection emits validation failed event."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_trunc_evt",
            provider_id="ov-truncevt-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_trunc_evt",
            _json_response({"text": "... [content truncated]"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_trunc_evt"))
        assert result.success is False

        # Validation fallback emits directly on event_port with EVENT_VALIDATION_FAILED
        failed_events = fabric.event_port.get_captured(topic=EVENT_VALIDATION_FAILED)
        assert len(failed_events) >= 1
        _, payload = failed_events[0]
        assert payload["tier"] == "STRUCTURAL"

    @pytest.mark.asyncio
    async def test_oversized_output_rejected(self) -> None:
        """Output exceeding 1MiB size limit is rejected at structural tier."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_oversize",
            provider_id="ov-oversize-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Create response data exceeding 1MiB
        large_data = {"payload": "x" * (DEFAULT_MAX_DATA_BYTES + 100)}
        transport.add_response(
            "tool.execute.ov_oversize",
            _json_response(large_data),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_oversize"))
        assert_capability_result_failure(result, error_code="output_validation_failed")

    @pytest.mark.asyncio
    async def test_nested_truncation_detected(self) -> None:
        """Truncation markers in nested dict values are detected."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_nested_trunc",
            provider_id="ov-nested-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_nested_trunc",
            _json_response({"outer": {"inner": "Some data... [output cut]"}}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_nested_trunc"))
        assert_capability_result_failure(result, error_code="output_validation_failed")

    @pytest.mark.asyncio
    async def test_structural_rejection_includes_learning_signal(self) -> None:
        """Learning signal is emitted even when output validation fails."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_trunc_learn",
            provider_id="ov-trunclearn-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_trunc_learn",
            _json_response({"data": "[truncated]"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_trunc_learn"))
        assert result.success is False

        # Learning signal should still be emitted (success=False)
        signals = fabric.event_port.get_captured(topic=TOPIC_LEARNING_SIGNAL)
        assert len(signals) >= 1
        _, payload = signals[0]
        assert payload["success"] is False
        assert payload["capability_name"] == "tool.execute.ov_trunc_learn"


# =========================================================================
# 6.3.13c -- Schema validation rejects non-conforming output
# =========================================================================


class TestSchemaValidationRejects:
    """Verify that Tier 2 (schema) failures cause execution rejection."""

    @pytest.mark.asyncio
    async def test_missing_required_field_rejected(self) -> None:
        """Output missing required field that cannot be coerced is rejected."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        # Use a schema where the missing required field has a complex type
        # that coercion CANNOT fill (object with its own required sub-fields)
        contract = _make_contract(
            name="tool.execute.ov_schema_req",
            output_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "address": {
                        "type": "object",
                        "properties": {
                            "street": {"type": "string"},
                            "city": {"type": "string"},
                        },
                        "required": ["street", "city"],
                    },
                },
                "required": ["name", "address"],
                "additionalProperties": False,
            },
            provider_id="ov-schemareq-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Response is missing 'address' entirely and has extra field
        transport.add_response(
            "tool.execute.ov_schema_req",
            _json_response({"name": "Alice", "unexpected": True}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_schema_req"))
        assert_capability_result_failure(result, error_code="output_validation_failed")

    @pytest.mark.asyncio
    async def test_wrong_type_rejected(self) -> None:
        """Output with wrong property type is rejected at schema tier."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_schema_type",
            output_schema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                },
                "required": ["count"],
            },
            provider_id="ov-schematype-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Response has string where integer expected, and NOT coercible
        transport.add_response(
            "tool.execute.ov_schema_type",
            _json_response({"count": "not_a_number"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_schema_type"))
        assert_capability_result_failure(result, error_code="output_validation_failed")

    @pytest.mark.asyncio
    async def test_additional_properties_false_rejects_extra(self) -> None:
        """additionalProperties=false rejects output with extra fields."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_schema_strict",
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                },
                "required": ["status"],
                "additionalProperties": False,
            },
            provider_id="ov-strict-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_schema_strict",
            _json_response({"status": "ok", "secret": "leaked"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_schema_strict"))
        assert_capability_result_failure(result, error_code="output_validation_failed")

    @pytest.mark.asyncio
    async def test_schema_rejection_emits_event(self) -> None:
        """Schema rejection emits validation failed event with SCHEMA tier."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        # additionalProperties=False prevents coercion from saving this
        contract = _make_contract(
            name="tool.execute.ov_schema_evt",
            output_schema={
                "type": "object",
                "properties": {
                    "value": {"type": "number"},
                },
                "required": ["value"],
                "additionalProperties": False,
            },
            provider_id="ov-schemaevt-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_schema_evt",
            _json_response({"wrong_field": "wrong"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_schema_evt"))
        assert result.success is False

        failed_events = fabric.event_port.get_captured(topic=EVENT_VALIDATION_FAILED)
        assert len(failed_events) >= 1
        _, payload = failed_events[0]
        assert payload["tier"] == "SCHEMA"

    @pytest.mark.asyncio
    async def test_array_min_items_violation(self) -> None:
        """Array output with too few items is rejected by schema."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_schema_arr",
            output_schema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "minItems": 3,
                        "items": {"type": "string"},
                    },
                },
                "required": ["items"],
            },
            provider_id="ov-schemaarr-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_schema_arr",
            _json_response({"items": ["only_one"]}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_schema_arr"))
        assert_capability_result_failure(result, error_code="output_validation_failed")

    @pytest.mark.asyncio
    async def test_nested_schema_violation_rejected(self) -> None:
        """Nested property type mismatch is detected by schema validator."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_schema_nested",
            output_schema={
                "type": "object",
                "properties": {
                    "meta": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "number"},
                        },
                        "required": ["score"],
                    },
                },
                "required": ["meta"],
            },
            provider_id="ov-schemanested-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_schema_nested",
            _json_response({"meta": {"score": "not_a_number"}}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_schema_nested"))
        assert_capability_result_failure(result, error_code="output_validation_failed")


# =========================================================================
# 6.3.13d -- Schema coercion: fixable violations are auto-repaired
# =========================================================================


class TestSchemaCoercion:
    """Verify that minor schema violations are auto-coerced."""

    @pytest.mark.asyncio
    async def test_missing_field_with_default_is_coerced(self) -> None:
        """Missing required field with schema default is filled by coercion."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_coerce_default",
            output_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string", "default": "user"},
                },
                "required": ["name", "role"],
            },
            provider_id="ov-coercedef-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Response missing 'role' -- coercion should fill default
        transport.add_response(
            "tool.execute.ov_coerce_default",
            _json_response({"name": "Alice"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_coerce_default"))
        assert_capability_result_success(result)
        assert result.data["name"] == "Alice"
        assert result.data["role"] == "user"

    @pytest.mark.asyncio
    async def test_string_to_number_coercion(self) -> None:
        """String value coerced to number when schema expects number."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_coerce_num",
            output_schema={
                "type": "object",
                "properties": {
                    "score": {"type": "number"},
                },
                "required": ["score"],
            },
            provider_id="ov-coercenum-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Send "42.5" as string -- coercion should cast to float
        transport.add_response(
            "tool.execute.ov_coerce_num",
            _json_response({"score": "42.5"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_coerce_num"))
        assert_capability_result_success(result)
        assert result.data["score"] == 42.5

    @pytest.mark.asyncio
    async def test_string_to_integer_coercion(self) -> None:
        """String value coerced to integer when schema expects integer."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_coerce_int",
            output_schema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                },
                "required": ["count"],
            },
            provider_id="ov-coerceint-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_coerce_int",
            _json_response({"count": "99"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_coerce_int"))
        assert_capability_result_success(result)
        assert result.data["count"] == 99

    @pytest.mark.asyncio
    async def test_missing_string_field_coerced_to_empty(self) -> None:
        """Missing required string field with no default is filled as empty string."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_coerce_str",
            output_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                },
                "required": ["title", "subtitle"],
            },
            provider_id="ov-coercestr-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Missing 'subtitle' -- coercion fills ""
        transport.add_response(
            "tool.execute.ov_coerce_str",
            _json_response({"title": "Hello"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_coerce_str"))
        assert_capability_result_success(result)
        assert result.data["title"] == "Hello"
        assert result.data["subtitle"] == ""

    @pytest.mark.asyncio
    async def test_coercion_does_not_emit_validation_failed(self) -> None:
        """Successful coercion should NOT emit validation failed event."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_coerce_noevt",
            output_schema={
                "type": "object",
                "properties": {
                    "val": {"type": "number"},
                },
                "required": ["val"],
            },
            provider_id="ov-coercenoevt-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_coerce_noevt",
            _json_response({"val": "3.14"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_coerce_noevt"))
        assert_capability_result_success(result)

        # No validation failed event on successful coercion
        failed_events = fabric.event_port.get_captured(topic=EVENT_VALIDATION_FAILED)
        assert len(failed_events) == 0


# =========================================================================
# 6.3.13e -- Validation interaction with execution pipeline
# =========================================================================


class TestValidationPipelineInteraction:
    """Verify how output validation interacts with the overall pipeline."""

    @pytest.mark.asyncio
    async def test_failed_execution_skips_validation(self) -> None:
        """Provider returning error skips output validation entirely."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_skip_err",
            provider_id="ov-skiperr-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Inject error response
        transport.add_response(
            "tool.execute.ov_skip_err",
            MCPResponse(
                success=False,
                error_message="Tool failed",
                latency_ms=1,
            ),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_skip_err"))
        assert result.success is False
        assert result.error.code == "mcp_tool_error"

        # No structural/schema validation events should be emitted
        failed_events = fabric.event_port.get_captured(topic=EVENT_VALIDATION_FAILED)
        assert len(failed_events) == 0

    @pytest.mark.asyncio
    async def test_validation_failure_reports_correct_error_code(self) -> None:
        """Validation failure produces error_code='output_validation_failed'."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_errcode",
            output_schema={
                "type": "object",
                "properties": {
                    "required_field": {"type": "string"},
                },
                "required": ["required_field"],
                "additionalProperties": False,
            },
            provider_id="ov-errcode-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_errcode",
            _json_response({"wrong_field": "data"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_errcode"))
        assert_capability_result_failure(result, error_code="output_validation_failed")
        assert result.error.retriable is False

    @pytest.mark.asyncio
    async def test_validation_rejection_still_emits_learning_signal(self) -> None:
        """Even when output is rejected, learning signal with success=False is emitted."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_rej_learn",
            output_schema={
                "type": "object",
                "properties": {
                    "value": {"type": "integer"},
                },
                "required": ["value"],
                "additionalProperties": False,
            },
            provider_id="ov-rejlearn-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_rej_learn",
            _json_response({"completely_wrong": True}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_rej_learn"))
        assert result.success is False

        signals = fabric.event_port.get_captured(topic=TOPIC_LEARNING_SIGNAL)
        assert len(signals) >= 1
        _, payload = signals[0]
        assert payload["success"] is False
        assert payload["error_code"] == "output_validation_failed"

    @pytest.mark.asyncio
    async def test_multiple_truncation_markers_in_response(self) -> None:
        """Multiple truncation variants are all detected."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_multi_trunc",
            provider_id="ov-multitrunc-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_multi_trunc",
            _json_response(
                {
                    "part1": "data...",
                    "part2": "more stuff",
                }
            ),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_multi_trunc"))
        assert_capability_result_failure(result, error_code="output_validation_failed")

    @pytest.mark.asyncio
    async def test_plain_text_response_passes_generic_schema(self) -> None:
        """Plain text MCP response produces {"result": text} which passes generic object schema."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        contract = _make_contract(
            name="tool.execute.ov_plain_text",
            output_schema={"type": "object"},
            provider_id="ov-plaintext-provider",
        )
        register_contract_with_provider(fabric, contract)

        transport.add_response(
            "tool.execute.ov_plain_text",
            _text_response("Hello world"),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_plain_text"))
        assert_capability_result_success(result)
        assert result.data["result"] == "Hello world"

    @pytest.mark.asyncio
    async def test_structural_runs_before_schema(self) -> None:
        """Structural rejection takes precedence over schema rejection."""
        transport = _make_transport()
        fabric = _make_fabric(transport)

        # Contract with strict output schema
        contract = _make_contract(
            name="tool.execute.ov_tier_order",
            output_schema={
                "type": "object",
                "properties": {
                    "required_val": {"type": "string"},
                },
                "required": ["required_val"],
            },
            provider_id="ov-tierorder-provider",
        )
        register_contract_with_provider(fabric, contract)

        # Response fails BOTH structural (truncation) AND schema (missing field)
        transport.add_response(
            "tool.execute.ov_tier_order",
            _json_response({"bad": "[truncated]"}),
        )

        result = await fabric.execute(_make_request("tool.execute.ov_tier_order"))
        assert result.success is False

        # Event should show STRUCTURAL tier (first check)
        failed_events = fabric.event_port.get_captured(topic=EVENT_VALIDATION_FAILED)
        assert len(failed_events) >= 1
        _, payload = failed_events[0]
        assert payload["tier"] == "STRUCTURAL"
