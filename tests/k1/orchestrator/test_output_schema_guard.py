"""
Tests for OutputSchemaGuard and DAGGuard base class (Issue 3.2.1 / ORCH-15).

Test classes:
  TestDAGGuardBase              -- ABC default implementations return CONTINUE/[].
  TestValidateSchemaHelper      -- _validate_schema() unit tests.
  TestOutputSchemaGuardNoSchema -- BYPASS when output_schema is None.
  TestOutputSchemaGuardFailed   -- CONTINUE when step not COMPLETED.
  TestOutputSchemaGuardValid    -- CONTINUE when data matches schema.
  TestOutputSchemaGuardRetry    -- RETRY on first schema failure.
  TestOutputSchemaGuardHardStop -- HARD_STOP when retry already used.
  TestOutputSchemaGuardNoneData -- RETRY/HARD_STOP when result.data is None.
  TestOutputSchemaGuardMalformed -- Handles malformed schema gracefully.
  TestOutputSchemaGuardMetadata -- Metadata contains validation_error key.
  TestGuardRepr                 -- __repr__ coverage.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.types import CapabilityResult
from k1.orchestrator.orchestration.guards import DAGGuard, OutputSchemaGuard
from k1.orchestrator.orchestration.guards.output_schema_guard import _validate_schema
from k1.orchestrator.types import (
    GuardAction,
    GuardDecision,
    PlanStep,
    ProcessingContext,
    StepResult,
    StepStatus,
    Wave,
    WaveResult,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_step(
    step_id: str = "s1",
    capability: str = "cap.test",
    params: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
) -> PlanStep:
    """Create a minimal PlanStep for guard tests."""
    return PlanStep(
        id=step_id,
        capability=capability,
        params=params or {"key": "val"},
        deps=[],
        output_schema=output_schema,
    )


def _make_result(
    step_id: str = "s1",
    capability: str = "cap.test",
    status: StepStatus = StepStatus.COMPLETED,
    data: Optional[Dict[str, Any]] = None,
    schema_retry: bool = False,
    error_detail: Optional[str] = None,
) -> StepResult:
    """Create a StepResult wrapping a CapabilityResult."""
    cap_result = None
    if data is not None or status == StepStatus.COMPLETED:
        cap_result = CapabilityResult(
            request_id="req-1",
            trace_id="t1",
            success=(status == StepStatus.COMPLETED),
            data=data,
            provider_id="test-provider",
            duration_ms=10,
        )
    return StepResult(
        step_id=step_id,
        capability_name=capability,
        status=status,
        duration_ms=10,
        result=cap_result,
        schema_retry=schema_retry,
        error_detail=error_detail,
    )


def _make_ctx() -> ProcessingContext:
    """Create a minimal ProcessingContext."""
    return ProcessingContext(
        trace_id="trace-1",
        request_id="req-1",
        tier="standard",
    )


def _make_wave(steps: Optional[List[PlanStep]] = None) -> Wave:
    """Create a minimal Wave."""
    return Wave(
        wave_index=0,
        steps=steps or [_make_step()],
        resolved_params={},
    )


def _make_wave_result() -> WaveResult:
    """Create a minimal WaveResult."""
    return WaveResult(
        wave_index=0,
        step_results=[_make_result()],
        duration_ms=10,
    )


# Simple valid schema for tests
SIMPLE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
    },
    "required": ["name"],
}


# ===========================================================================
# DAGGuard Base Class Tests
# ===========================================================================


class TestDAGGuardBase:
    """Test DAGGuard ABC default implementations."""

    @pytest.fixture
    def guard(self) -> DAGGuard:
        """Concrete subclass with no overrides to test defaults."""

        class _NoOpGuard(DAGGuard):
            pass

        return _NoOpGuard()

    async def test_before_wave_returns_empty_list(self, guard: DAGGuard) -> None:
        wave = _make_wave()
        ctx = _make_ctx()
        decisions = await guard.before_wave(wave, ctx)
        assert decisions == []
        assert isinstance(decisions, list)

    async def test_after_step_returns_continue(self, guard: DAGGuard) -> None:
        step = _make_step()
        result = _make_result()
        ctx = _make_ctx()
        decision = await guard.after_step(step, result, ctx)
        assert isinstance(decision, GuardDecision)
        assert decision.action == GuardAction.CONTINUE
        assert decision.guard_name == "_NoOpGuard"

    async def test_after_wave_returns_continue(self, guard: DAGGuard) -> None:
        wave_result = _make_wave_result()
        ctx = _make_ctx()
        decision = await guard.after_wave(wave_result, ctx)
        assert isinstance(decision, GuardDecision)
        assert decision.action == GuardAction.CONTINUE
        assert decision.guard_name == "_NoOpGuard"

    def test_repr(self, guard: DAGGuard) -> None:
        assert repr(guard) == "_NoOpGuard()"

    def test_cannot_instantiate_abc_directly(self) -> None:
        """DAGGuard is abstract but has no abstract methods, so it CAN
        be instantiated.  The ABC marker is for type-checking intent."""

        # DAGGuard has no @abstractmethod, so direct instantiation works.
        # This is by design: guards override only hooks they need.
        class _Concrete(DAGGuard):
            pass

        g = _Concrete()
        assert isinstance(g, DAGGuard)


# ===========================================================================
# _validate_schema Helper Tests
# ===========================================================================


class TestValidateSchemaHelper:
    """Unit tests for the _validate_schema() standalone helper."""

    def test_valid_data_returns_none(self) -> None:
        data = {"name": "Alice", "age": 30}
        assert _validate_schema(data, SIMPLE_SCHEMA) is None

    def test_valid_data_minimal_required(self) -> None:
        data = {"name": "Bob"}  # age is optional
        assert _validate_schema(data, SIMPLE_SCHEMA) is None

    def test_none_data_returns_error(self) -> None:
        result = _validate_schema(None, SIMPLE_SCHEMA)
        assert result is not None
        assert "no output data" in result.lower()

    def test_missing_required_field(self) -> None:
        data = {"age": 25}  # missing required 'name'
        result = _validate_schema(data, SIMPLE_SCHEMA)
        assert result is not None
        assert "name" in result.lower() or "required" in result.lower()

    def test_wrong_type_returns_error(self) -> None:
        data = {"name": 123}  # should be string
        result = _validate_schema(data, SIMPLE_SCHEMA)
        assert result is not None
        assert "name" in result.lower() or "type" in result.lower()

    def test_extra_properties_allowed_by_default(self) -> None:
        data = {"name": "Alice", "extra": True}
        assert _validate_schema(data, SIMPLE_SCHEMA) is None

    def test_additional_properties_false(self) -> None:
        strict_schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        }
        data = {"name": "Alice", "extra": True}
        result = _validate_schema(data, strict_schema)
        assert result is not None
        assert "additional" in result.lower() or "extra" in result.lower()

    def test_nested_object_validation(self) -> None:
        nested_schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                    "required": ["id"],
                }
            },
            "required": ["user"],
        }
        # valid
        assert _validate_schema({"user": {"id": 42}}, nested_schema) is None
        # invalid nested
        result = _validate_schema({"user": {"id": "not-int"}}, nested_schema)
        assert result is not None
        assert "user" in result or "id" in result

    def test_malformed_schema_returns_error(self) -> None:
        """A schema with invalid structure should not raise, should return error."""
        bad_schema: Dict[str, Any] = {"type": "bogus_not_a_type"}
        data = {"anything": True}
        result = _validate_schema(data, bad_schema)
        # jsonschema may or may not raise SchemaError vs ValidationError
        # depending on draft detection; either way we get a truthy string
        assert result is not None

    def test_empty_object_schema(self) -> None:
        """Empty schema {} validates anything."""
        assert _validate_schema({"a": 1}, {}) is None
        assert _validate_schema({}, {}) is None

    def test_array_schema(self) -> None:
        schema = {"type": "array", "items": {"type": "integer"}}
        # The data dict is not an array -> should fail
        result = _validate_schema({"not": "array"}, schema)
        assert result is not None


# ===========================================================================
# OutputSchemaGuard Tests
# ===========================================================================


class TestOutputSchemaGuardNoSchema:
    """BYPASS when step has no output_schema."""

    async def test_no_schema_returns_bypass(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=None)
        result = _make_result()
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.BYPASS
        assert decision.guard_name == "OutputSchemaGuard"
        assert "no output_schema" in decision.reason.lower()


class TestOutputSchemaGuardFailed:
    """CONTINUE when the step did not complete successfully."""

    @pytest.mark.parametrize(
        "status",
        [StepStatus.FAILED, StepStatus.CANCELLED, StepStatus.SKIPPED, StepStatus.PENDING],
    )
    async def test_non_completed_status_returns_continue(self, status: StepStatus) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = StepResult(
            step_id="s1",
            capability_name="cap.test",
            status=status,
            duration_ms=10,
            error_detail="some error" if status == StepStatus.FAILED else None,
        )
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.CONTINUE
        assert "already failed" in decision.reason.lower() or "skipped" in decision.reason.lower()


class TestOutputSchemaGuardValid:
    """CONTINUE when step output matches the schema."""

    async def test_valid_output_returns_continue(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = _make_result(data={"name": "Alice", "age": 30})
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.CONTINUE
        assert "matches schema" in decision.reason.lower()

    async def test_valid_output_minimal_required(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = _make_result(data={"name": "Bob"})
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.CONTINUE


class TestOutputSchemaGuardRetry:
    """RETRY on first schema validation failure."""

    async def test_invalid_output_first_attempt_returns_retry(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = _make_result(data={"age": 30}, schema_retry=False)  # missing 'name'
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.RETRY
        assert "validation_error" in decision.metadata

    async def test_wrong_type_first_attempt_returns_retry(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = _make_result(data={"name": 42}, schema_retry=False)
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.RETRY


class TestOutputSchemaGuardHardStop:
    """HARD_STOP when schema retry already used and still invalid."""

    async def test_invalid_after_retry_returns_hard_stop(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = _make_result(data={"age": 30}, schema_retry=True)  # retried + still bad
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.HARD_STOP
        assert "after retry" in decision.reason.lower()
        assert "validation_error" in decision.metadata


class TestOutputSchemaGuardNoneData:
    """RETRY/HARD_STOP when result.data is None but schema is defined."""

    async def test_none_data_first_attempt_returns_retry(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        # COMPLETED but result has no data (CapabilityResult.data=None)
        result = _make_result(data=None, schema_retry=False)
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.RETRY

    async def test_none_data_after_retry_returns_hard_stop(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = _make_result(data=None, schema_retry=True)
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.HARD_STOP

    async def test_none_cap_result_first_attempt_returns_retry(self) -> None:
        """When result.result is None (no CapabilityResult at all)."""
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = StepResult(
            step_id="s1",
            capability_name="cap.test",
            status=StepStatus.COMPLETED,
            duration_ms=10,
            result=None,  # No CapabilityResult
            schema_retry=False,
        )
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.RETRY


class TestOutputSchemaGuardMalformed:
    """Test handling of malformed schemas."""

    async def test_malformed_schema_returns_retry_first(self) -> None:
        """Malformed schema is treated as validation error -> RETRY/HARD_STOP."""
        guard = OutputSchemaGuard()
        # type: "bogus" is not a recognized JSON Schema type
        step = _make_step(output_schema={"type": "bogus_type"})
        result = _make_result(data={"anything": True}, schema_retry=False)
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        # Should be a failure action (either RETRY or HARD_STOP depending on error)
        assert decision.action in (GuardAction.RETRY, GuardAction.HARD_STOP)

    async def test_malformed_schema_after_retry_returns_hard_stop(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema={"type": "bogus_type"})
        result = _make_result(data={"anything": True}, schema_retry=True)
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action in (GuardAction.RETRY, GuardAction.HARD_STOP)


class TestOutputSchemaGuardMetadata:
    """Validate metadata on RETRY and HARD_STOP decisions."""

    async def test_retry_metadata_has_validation_error(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = _make_result(data={}, schema_retry=False)
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.RETRY
        assert "validation_error" in decision.metadata
        assert isinstance(decision.metadata["validation_error"], str)
        assert len(decision.metadata["validation_error"]) > 0

    async def test_hard_stop_metadata_has_validation_error(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = _make_result(data={}, schema_retry=True)
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.HARD_STOP
        assert "validation_error" in decision.metadata
        assert isinstance(decision.metadata["validation_error"], str)

    async def test_continue_has_no_metadata(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=SIMPLE_SCHEMA)
        result = _make_result(data={"name": "Alice"})
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.CONTINUE
        # GuardDecision.metadata defaults to empty dict
        assert not decision.metadata or "validation_error" not in decision.metadata

    async def test_bypass_has_no_metadata(self) -> None:
        guard = OutputSchemaGuard()
        step = _make_step(output_schema=None)
        result = _make_result()
        ctx = _make_ctx()

        decision = await guard.after_step(step, result, ctx)

        assert decision.action == GuardAction.BYPASS
        assert not decision.metadata or "validation_error" not in decision.metadata


class TestGuardRepr:
    """__repr__ coverage for both guard classes."""

    def test_output_schema_guard_repr(self) -> None:
        assert repr(OutputSchemaGuard()) == "OutputSchemaGuard()"

    def test_dag_guard_subclass_repr(self) -> None:
        class MyCustomGuard(DAGGuard):
            pass

        assert repr(MyCustomGuard()) == "MyCustomGuard()"


# ===========================================================================
# Integration: Complex Schema Tests
# ===========================================================================


class TestComplexSchemaValidation:
    """Integration tests with more complex JSON Schemas."""

    async def test_deeply_nested_schema(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "number", "minimum": 0},
                            },
                            "required": ["value"],
                        }
                    },
                    "required": ["level2"],
                }
            },
            "required": ["level1"],
        }
        guard = OutputSchemaGuard()
        ctx = _make_ctx()

        # Valid
        step = _make_step(output_schema=schema)
        result = _make_result(data={"level1": {"level2": {"value": 42}}})
        decision = await guard.after_step(step, result, ctx)
        assert decision.action == GuardAction.CONTINUE

        # Invalid (negative value)
        result_bad = _make_result(data={"level1": {"level2": {"value": -1}}})
        decision_bad = await guard.after_step(step, result_bad, ctx)
        assert decision_bad.action == GuardAction.RETRY

    async def test_enum_schema(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "inactive"]},
            },
            "required": ["status"],
        }
        guard = OutputSchemaGuard()
        ctx = _make_ctx()
        step = _make_step(output_schema=schema)

        # Valid
        result = _make_result(data={"status": "active"})
        assert (await guard.after_step(step, result, ctx)).action == GuardAction.CONTINUE

        # Invalid enum value
        result_bad = _make_result(data={"status": "unknown"})
        assert (await guard.after_step(step, result_bad, ctx)).action == GuardAction.RETRY

    async def test_array_items_schema(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                }
            },
            "required": ["items"],
        }
        guard = OutputSchemaGuard()
        ctx = _make_ctx()
        step = _make_step(output_schema=schema)

        # Valid
        result = _make_result(data={"items": ["a", "b"]})
        assert (await guard.after_step(step, result, ctx)).action == GuardAction.CONTINUE

        # Empty array (below minItems)
        result_bad = _make_result(data={"items": []})
        assert (await guard.after_step(step, result_bad, ctx)).action == GuardAction.RETRY

        # Wrong item type
        result_bad2 = _make_result(data={"items": [1, 2]})
        assert (await guard.after_step(step, result_bad2, ctx)).action == GuardAction.RETRY

    async def test_guard_name_always_output_schema_guard(self) -> None:
        """Every decision from OutputSchemaGuard has correct guard_name."""
        guard = OutputSchemaGuard()
        ctx = _make_ctx()

        decisions = [
            await guard.after_step(_make_step(output_schema=None), _make_result(), ctx),
            await guard.after_step(
                _make_step(output_schema=SIMPLE_SCHEMA),
                _make_result(data={"name": "ok"}),
                ctx,
            ),
            await guard.after_step(
                _make_step(output_schema=SIMPLE_SCHEMA),
                _make_result(data={}, schema_retry=False),
                ctx,
            ),
            await guard.after_step(
                _make_step(output_schema=SIMPLE_SCHEMA),
                _make_result(data={}, schema_retry=True),
                ctx,
            ),
        ]

        for decision in decisions:
            assert decision.guard_name == "OutputSchemaGuard"
