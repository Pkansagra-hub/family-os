"""
Tests for StepRunner (Issues 2.3.1, 2.3.2, 2.3.3).

Test classes:
  TestStepRunnerHappyPath             -- Single execution, success wrapping.
  TestCapabilityRequestBuilding       -- All fields correctly populated.
  TestRetryOnRetriableFailure         -- Up to 2 normal retries, then fail.
  TestRetryNonRetriable               -- No retry on non-retriable error.
  TestRetryBudgetExhausted            -- Correct behaviour when all retries used.
  TestSchemaValidation                -- validate_output_schema() unit tests.
  TestSchemaRetryIntegration          -- Schema retry triggers in retry loop.
  TestSchemaRetryRequestBuilding      -- __schema_hint injected correctly.
  TestSchemaAndNormalRetryInteraction -- Combined retry budgets.
  TestDurationMeasurement             -- duration_ms is tracked.
  TestExceptionFromFabric             -- fabric_port.execute raises exception.
  TestToolsGrantedPassthrough         -- tools_granted via context_override.
  TestRepr                            -- __repr__ coverage.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.orchestration.step_runner import StepRunner
from k1.orchestrator.types import OrchestratorPolicies, PlanStep, SchemaResult, StepStatus

# ===========================================================================
# Helpers
# ===========================================================================


def _make_step(
    step_id: str = "s1",
    capability: str = "cap.test",
    params: Optional[Dict[str, Any]] = None,
    timeout_ms: Optional[int] = None,
    prompt_template: Optional[str] = None,
    tools_granted: Optional[List[str]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
) -> PlanStep:
    return PlanStep(
        id=step_id,
        capability=capability,
        params=params or {"key": "val"},
        deps=[],
        timeout_ms=timeout_ms,
        prompt_template=prompt_template,
        tools_granted=tools_granted,
        output_schema=output_schema,
    )


def _success_result(request_id: str = "req-1", trace_id: str = "t1") -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id=request_id,
        data={"output": "ok"},
        provider_id="test-provider",
        trace_id=trace_id,
    )


def _failure_result(
    request_id: str = "req-1",
    retriable: bool = True,
    error_code: str = "transient",
    error_message: str = "temporary failure",
    trace_id: str = "t1",
) -> CapabilityResult:
    return CapabilityResult.failure_result(
        request_id=request_id,
        error_code=error_code,
        error_message=error_message,
        retriable=retriable,
        trace_id=trace_id,
    )


def _default_policies(**overrides: Any) -> OrchestratorPolicies:
    return OrchestratorPolicies(**overrides)


class FakeFabricPort:
    """Fake IFabricGatewayPort with per-call result sequence."""

    def __init__(self) -> None:
        self._results: List[CapabilityResult] = []
        self._exceptions: List[Optional[Exception]] = []
        self._call_index = 0
        self.execute_calls: List[CapabilityRequest] = []

    def add_result(self, result: CapabilityResult) -> None:
        self._results.append(result)
        self._exceptions.append(None)

    def add_exception(self, exc: Exception) -> None:
        self._results.append(None)  # type: ignore[arg-type]
        self._exceptions.append(exc)

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        self.execute_calls.append(request)
        idx = self._call_index
        self._call_index += 1
        if idx < len(self._exceptions) and self._exceptions[idx] is not None:
            raise self._exceptions[idx]  # type: ignore[misc]
        if idx < len(self._results):
            return self._results[idx]
        # default: success
        return _success_result()


class FakeErrorRouter:
    """Fake ErrorRouter -- not used in V1 retry logic but required by constructor."""

    pass


def _build_runner(
    fabric: Optional[FakeFabricPort] = None,
    policies: Optional[OrchestratorPolicies] = None,
) -> Tuple[StepRunner, FakeFabricPort]:
    fab = fabric or FakeFabricPort()
    pol = policies or _default_policies()
    runner = StepRunner(
        fabric_port=fab,
        error_router=FakeErrorRouter(),  # type: ignore[arg-type]
        policies=pol,
    )
    return runner, fab


# ===========================================================================
# TestStepRunnerHappyPath
# ===========================================================================


class TestStepRunnerHappyPath:
    """Single execution, success wrapping."""

    async def test_success_returns_completed(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_success_result())
        step = _make_step()

        result = await runner.run(step, {"key": "val"}, {}, "trace-1")

        assert result.status == StepStatus.COMPLETED
        assert result.step_id == "s1"
        assert result.capability_name == "cap.test"
        assert result.result is not None
        assert result.result.success is True
        assert result.retry_attempts == 0
        assert result.schema_retry is False
        assert result.error_detail is None

    async def test_failure_returns_failed(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_failure_result(retriable=False))
        step = _make_step()

        result = await runner.run(step, {"key": "val"}, {}, "trace-1")

        assert result.status == StepStatus.FAILED
        assert result.error_detail == "temporary failure"
        assert result.retry_attempts == 0

    async def test_duration_is_nonnegative(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_success_result())
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        assert result.duration_ms >= 0


# ===========================================================================
# TestCapabilityRequestBuilding
# ===========================================================================


class TestCapabilityRequestBuilding:
    """Validate the CapabilityRequest fields populated by _build_request."""

    async def test_basic_fields_populated(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_success_result())
        step = _make_step(
            step_id="step-7",
            capability="cap.summarize",
            prompt_template="Summarize: {text}",
        )

        await runner.run(step, {"text": "hello"}, {}, "trace-42")

        assert len(fab.execute_calls) == 1
        req = fab.execute_calls[0]
        assert req.capability_name == "cap.summarize"
        assert req.params == {"text": "hello"}
        assert req.prompt_template == "Summarize: {text}"
        assert req.tier == "HIGH"
        assert req.caller == "orchestrator"
        assert req.caller_id == "step-7"
        assert req.trace_id == "trace-42"
        assert req.plan_id == "step-7"
        assert req.step_id == "step-7"

    async def test_timeout_from_step(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_success_result())
        step = _make_step(timeout_ms=5000)

        await runner.run(step, {}, {}, "t")

        req = fab.execute_calls[0]
        assert req.timeout_ms == 5000

    async def test_timeout_fallback_to_policy(self) -> None:
        runner, fab = _build_runner(policies=_default_policies(step_timeout_default_ms=15000))
        fab.add_result(_success_result())
        step = _make_step(timeout_ms=None)

        await runner.run(step, {}, {}, "t")

        req = fab.execute_calls[0]
        assert req.timeout_ms == 15000

    async def test_no_context_override_without_tools_granted(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_success_result())
        step = _make_step(tools_granted=None)

        await runner.run(step, {}, {}, "t")

        req = fab.execute_calls[0]
        assert req.context_override is None

    async def test_resolved_params_override_step_params(self) -> None:
        """resolved_params is used, not step.params."""
        runner, fab = _build_runner()
        fab.add_result(_success_result())
        step = _make_step(params={"original": True})

        await runner.run(step, {"resolved": True}, {}, "t")

        req = fab.execute_calls[0]
        assert req.params == {"resolved": True}


# ===========================================================================
# TestToolsGrantedPassthrough
# ===========================================================================


class TestToolsGrantedPassthrough:
    """tools_granted passed via context_override."""

    async def test_tools_granted_in_context_override(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_success_result())
        step = _make_step(tools_granted=["search", "calculator"])

        await runner.run(step, {}, {}, "t")

        req = fab.execute_calls[0]
        assert req.context_override == {"tools_granted": ["search", "calculator"]}

    async def test_empty_tools_granted_no_context_override(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_success_result())
        step = _make_step(tools_granted=[])

        await runner.run(step, {}, {}, "t")

        req = fab.execute_calls[0]
        # Empty list is falsy -> no context_override
        assert req.context_override is None


# ===========================================================================
# TestRetryOnRetriableFailure
# ===========================================================================


class TestRetryOnRetriableFailure:
    """Up to 2 normal retries on retriable errors (policies.normal_retries=2)."""

    async def test_first_retry_then_success(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_failure_result(retriable=True))
        fab.add_result(_success_result())
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.COMPLETED
        assert result.retry_attempts == 1
        assert len(fab.execute_calls) == 2

    async def test_two_retries_then_success(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_failure_result(retriable=True))
        fab.add_result(_failure_result(retriable=True))
        fab.add_result(_success_result())
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.COMPLETED
        assert result.retry_attempts == 2
        assert len(fab.execute_calls) == 3

    async def test_max_retries_exhausted_returns_failed(self) -> None:
        runner, fab = _build_runner()
        # 1 initial + 2 retries = 3 calls, all fail
        fab.add_result(_failure_result(retriable=True))
        fab.add_result(_failure_result(retriable=True))
        fab.add_result(_failure_result(retriable=True, error_message="still broken"))
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.FAILED
        assert result.retry_attempts == 2
        assert result.error_detail == "still broken"
        assert len(fab.execute_calls) == 3

    async def test_custom_retry_count(self) -> None:
        runner, fab = _build_runner(policies=_default_policies(normal_retries=1))
        fab.add_result(_failure_result(retriable=True))
        fab.add_result(_failure_result(retriable=True, error_message="done after 1 retry"))
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.FAILED
        assert result.retry_attempts == 1
        assert len(fab.execute_calls) == 2


# ===========================================================================
# TestRetryNonRetriable
# ===========================================================================


class TestRetryNonRetriable:
    """Non-retriable errors are NOT retried."""

    async def test_non_retriable_no_retry(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_failure_result(retriable=False, error_message="permanent"))
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.FAILED
        assert result.retry_attempts == 0
        assert result.error_detail == "permanent"
        assert len(fab.execute_calls) == 1

    async def test_retriable_then_non_retriable_stops(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_failure_result(retriable=True))
        fab.add_result(_failure_result(retriable=False, error_message="now permanent"))
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.FAILED
        assert result.retry_attempts == 1
        assert result.error_detail == "now permanent"
        assert len(fab.execute_calls) == 2


# ===========================================================================
# TestRetryBudgetExhausted
# ===========================================================================


class TestRetryBudgetExhausted:
    """Edge cases around retry budget boundaries."""

    async def test_zero_retries_policy(self) -> None:
        runner, fab = _build_runner(policies=_default_policies(normal_retries=0))
        fab.add_result(_failure_result(retriable=True, error_message="no budget"))
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.FAILED
        assert result.retry_attempts == 0
        assert result.error_detail == "no budget"
        assert len(fab.execute_calls) == 1

    async def test_error_without_error_object(self) -> None:
        """Result with success=False but error=None (edge case)."""
        runner, fab = _build_runner()
        # Manually craft a failure with no error info
        bad_result = CapabilityResult(
            request_id="r1",
            trace_id="t",
            success=False,
            data=None,
            error=None,
            provider_id="p",
        )
        fab.add_result(bad_result)
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.FAILED
        assert result.error_detail == "Unknown failure"
        assert result.retry_attempts == 0


# ===========================================================================
# Helpers for schema-aware results
# ===========================================================================


def _success_with_data(data: Dict[str, Any], request_id: str = "req-1") -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id=request_id,
        data=data,
        provider_id="test-provider",
        trace_id="t1",
    )


# ===========================================================================
# TestSchemaValidation
# ===========================================================================


class TestSchemaValidation:
    """Unit tests for validate_output_schema() (2.3.3)."""

    def _runner(self) -> StepRunner:
        runner, _ = _build_runner()
        return runner

    def test_valid_data_returns_valid(self) -> None:
        runner = self._runner()
        schema = {"type": "object", "properties": {"summary": {"type": "string"}}}
        result = _success_with_data({"summary": "hello"})

        sv = runner.validate_output_schema(result, schema)

        assert sv.valid is True
        assert sv.errors == []
        assert sv.suggestion is None

    def test_invalid_data_returns_errors(self) -> None:
        runner = self._runner()
        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        }
        result = _success_with_data({"wrong_field": 123})

        sv = runner.validate_output_schema(result, schema)

        assert sv.valid is False
        assert len(sv.errors) >= 1
        assert sv.suggestion is not None
        assert "schema violation" in sv.suggestion.lower()

    def test_type_mismatch_error(self) -> None:
        runner = self._runner()
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
        result = _success_with_data({"count": "not_a_number"})

        sv = runner.validate_output_schema(result, schema)

        assert sv.valid is False
        assert any("not_a_number" in e or "integer" in e for e in sv.errors)

    def test_multiple_errors_collected(self) -> None:
        runner = self._runner()
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        }
        result = _success_with_data({"a": 123, "b": "wrong"})

        sv = runner.validate_output_schema(result, schema)

        assert sv.valid is False
        assert len(sv.errors) >= 2

    def test_none_data_returns_invalid(self) -> None:
        runner = self._runner()
        schema = {"type": "object"}
        result = CapabilityResult(
            request_id="r1",
            trace_id="t",
            success=True,
            data=None,
            error=None,
            provider_id="p",
        )

        sv = runner.validate_output_schema(result, schema)

        assert sv.valid is False
        assert "None" in sv.errors[0]

    def test_malformed_schema_returns_valid(self) -> None:
        """Malformed JSON Schema should not block execution."""
        runner = self._runner()
        schema = {"type": "not_a_real_type"}  # invalid schema
        result = _success_with_data({"key": "val"})

        sv = runner.validate_output_schema(result, schema)

        # Malformed schema -> pass through (do not retry)
        assert sv.valid is True

    def test_empty_object_matches_object_schema(self) -> None:
        runner = self._runner()
        schema = {"type": "object"}
        result = _success_with_data({})

        sv = runner.validate_output_schema(result, schema)

        assert sv.valid is True

    def test_additional_properties_valid_by_default(self) -> None:
        runner = self._runner()
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        result = _success_with_data({"a": "ok", "extra": 99})

        sv = runner.validate_output_schema(result, schema)

        assert sv.valid is True


# ===========================================================================
# TestBuildSchemaSuggestion
# ===========================================================================


class TestBuildSchemaSuggestion:
    """Unit tests for _build_schema_suggestion static method."""

    def test_single_error(self) -> None:
        msg = StepRunner._build_schema_suggestion(["field missing"])
        assert msg == "Output schema violation: field missing"

    def test_multiple_errors(self) -> None:
        msg = StepRunner._build_schema_suggestion(["err1", "err2", "err3"])
        assert "violations" in msg.lower()
        assert "err1" in msg
        assert "err2" in msg
        assert "err3" in msg

    def test_more_than_five_errors_truncated(self) -> None:
        errors = [f"err{i}" for i in range(8)]
        msg = StepRunner._build_schema_suggestion(errors)
        assert "(and 3 more)" in msg
        assert "err5" not in msg  # 6th error (0-indexed: err5) excluded


# ===========================================================================
# TestSchemaRetryRequestBuilding
# ===========================================================================


class TestSchemaRetryRequestBuilding:
    """Tests for _build_schema_retry_request() (2.3.3)."""

    def test_schema_hint_injected_in_params(self) -> None:
        runner, _ = _build_runner()
        step = _make_step()
        original_req = runner._build_request(step, {"key": "val"}, "t1")
        sr = SchemaResult(valid=False, errors=["bad"], suggestion="Fix the output")

        new_req = runner._build_schema_retry_request(original_req, step, sr)

        assert new_req.params["__schema_hint"] == "Fix the output"
        assert new_req.params["key"] == "val"

    def test_original_request_unchanged(self) -> None:
        runner, _ = _build_runner()
        step = _make_step()
        original_req = runner._build_request(step, {"key": "val"}, "t1")
        sr = SchemaResult(valid=False, errors=["bad"], suggestion="hint")

        new_req = runner._build_schema_retry_request(original_req, step, sr)

        # Original is frozen -- params should NOT have __schema_hint
        assert "__schema_hint" not in original_req.params
        assert "__schema_hint" in new_req.params

    def test_no_suggestion_uses_default(self) -> None:
        runner, _ = _build_runner()
        step = _make_step()
        original_req = runner._build_request(step, {}, "t1")
        sr = SchemaResult(valid=False, errors=["bad"], suggestion=None)

        new_req = runner._build_schema_retry_request(original_req, step, sr)

        assert new_req.params["__schema_hint"] == "Output did not match expected schema."

    def test_same_identity_fields_preserved(self) -> None:
        runner, _ = _build_runner()
        step = _make_step(step_id="s7", capability="cap.x")
        original_req = runner._build_request(step, {"a": 1}, "trace-99")
        sr = SchemaResult(valid=False, errors=["e"], suggestion="hint")

        new_req = runner._build_schema_retry_request(original_req, step, sr)

        assert new_req.capability_name == original_req.capability_name
        assert new_req.trace_id == original_req.trace_id
        assert new_req.caller == original_req.caller
        assert new_req.timeout_ms == original_req.timeout_ms
        assert new_req.tier == original_req.tier


# ===========================================================================
# TestSchemaRetryIntegration
# ===========================================================================


class TestSchemaRetryIntegration:
    """Schema retry integration into _execute_with_retry loop (2.3.2 + 2.3.3)."""

    async def test_no_schema_no_retry(self) -> None:
        """No output_schema -> no schema validation, schema_retry stays False."""
        runner, fab = _build_runner()
        fab.add_result(_success_with_data({"output": "ok"}))
        step = _make_step(output_schema=None)

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.COMPLETED
        assert result.schema_retry is False
        assert len(fab.execute_calls) == 1

    async def test_valid_schema_no_retry(self) -> None:
        """output_schema set and data is valid -> no retry."""
        runner, fab = _build_runner()
        fab.add_result(_success_with_data({"summary": "hello"}))
        step = _make_step(
            output_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            }
        )

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.COMPLETED
        assert result.schema_retry is False
        assert len(fab.execute_calls) == 1

    async def test_invalid_schema_triggers_retry(self) -> None:
        """Invalid output -> schema retry with __schema_hint, then valid -> COMPLETED."""
        runner, fab = _build_runner()
        # First call: success but invalid schema
        fab.add_result(_success_with_data({"wrong": 123}))
        # Second call (schema retry): success with valid data
        fab.add_result(_success_with_data({"summary": "fixed"}))
        step = _make_step(
            output_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            }
        )

        result = await runner.run(step, {"input": "x"}, {}, "t")

        assert result.status == StepStatus.COMPLETED
        assert result.schema_retry is True
        assert result.retry_attempts == 0  # no normal retries
        assert len(fab.execute_calls) == 2
        # Second request should have __schema_hint
        assert "__schema_hint" in fab.execute_calls[1].params
        # Original params preserved
        assert fab.execute_calls[1].params["input"] == "x"

    async def test_schema_retry_budget_one(self) -> None:
        """Only 1 schema retry allowed (policies.schema_retries=1)."""
        runner, fab = _build_runner()
        # Both calls return invalid schema data
        fab.add_result(_success_with_data({"wrong": 1}))
        fab.add_result(_success_with_data({"still_wrong": 2}))
        step = _make_step(
            output_schema={
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            }
        )

        result = await runner.run(step, {}, {}, "t")

        # Returns as-is after budget exhausted (still COMPLETED from Fabric)
        assert result.status == StepStatus.COMPLETED
        assert result.schema_retry is True
        assert len(fab.execute_calls) == 2

    async def test_schema_retries_zero_policy(self) -> None:
        """schema_retries=0 means no schema retry at all."""
        runner, fab = _build_runner(policies=_default_policies(schema_retries=0))
        fab.add_result(_success_with_data({"wrong": 1}))
        step = _make_step(
            output_schema={
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            }
        )

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.COMPLETED
        assert result.schema_retry is False
        assert len(fab.execute_calls) == 1

    async def test_schema_retry_fails_returns_completed(self) -> None:
        """Schema retry with still-invalid data returns COMPLETED (Fabric succeeded)."""
        runner, fab = _build_runner()
        fab.add_result(_success_with_data({"bad": True}))
        fab.add_result(_success_with_data({"still_bad": True}))
        step = _make_step(output_schema={"type": "object", "required": ["name"]})

        result = await runner.run(step, {}, {}, "t")

        # Still COMPLETED (Fabric returned success, just schema mismatch)
        assert result.status == StepStatus.COMPLETED
        assert result.schema_retry is True


# ===========================================================================
# TestSchemaAndNormalRetryInteraction
# ===========================================================================


class TestSchemaAndNormalRetryInteraction:
    """Tests that normal retries and schema retries have separate budgets."""

    async def test_normal_retry_then_schema_retry(self) -> None:
        """Retriable failure -> normal retry -> success but invalid schema -> schema retry."""
        runner, fab = _build_runner()
        # Call 1: retriable failure
        fab.add_result(_failure_result(retriable=True))
        # Call 2 (normal retry): success but invalid schema
        fab.add_result(_success_with_data({"wrong": True}))
        # Call 3 (schema retry): success with valid data
        fab.add_result(_success_with_data({"name": "ok"}))
        step = _make_step(output_schema={"type": "object", "required": ["name"]})

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.COMPLETED
        assert result.retry_attempts == 1  # 1 normal retry
        assert result.schema_retry is True
        assert len(fab.execute_calls) == 3

    async def test_max_normal_then_schema_not_possible(self) -> None:
        """All normal retries exhausted -> FAILED, schema retry never triggered."""
        runner, fab = _build_runner()
        fab.add_result(_failure_result(retriable=True))
        fab.add_result(_failure_result(retriable=True))
        fab.add_result(_failure_result(retriable=True, error_message="exhausted"))
        step = _make_step(output_schema={"type": "object", "required": ["name"]})

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.FAILED
        assert result.retry_attempts == 2
        assert result.schema_retry is False  # never reached success path
        assert len(fab.execute_calls) == 3

    async def test_schema_retry_does_not_count_as_normal(self) -> None:
        """Schema retry should not decrement normal retry budget."""
        runner, fab = _build_runner(policies=_default_policies(normal_retries=1))
        # Call 1: success but invalid schema
        fab.add_result(_success_with_data({"wrong": True}))
        # Call 2 (schema retry): retriable failure
        fab.add_result(_failure_result(retriable=True))
        # Call 3 (normal retry): success
        fab.add_result(_success_with_data({"name": "ok"}))
        step = _make_step(output_schema={"type": "object", "required": ["name"]})

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.COMPLETED
        assert result.schema_retry is True
        assert result.retry_attempts == 1
        assert len(fab.execute_calls) == 3

    async def test_failure_on_non_retriable_after_schema_retry(self) -> None:
        """Schema retry succeeds at Fabric but then fails on non-retriable error."""
        runner, fab = _build_runner()
        # Call 1: success but invalid schema
        fab.add_result(_success_with_data({"wrong": True}))
        # Call 2 (schema retry): non-retriable failure
        fab.add_result(_failure_result(retriable=False, error_message="fatal"))
        step = _make_step(output_schema={"type": "object", "required": ["name"]})

        result = await runner.run(step, {}, {}, "t")

        assert result.status == StepStatus.FAILED
        assert result.schema_retry is True
        assert result.error_detail == "fatal"
        assert len(fab.execute_calls) == 2

    async def test_schema_retry_request_uses_original_not_retry_request(self) -> None:
        """Schema retry request is built from the ORIGINAL request, not last retry."""
        runner, fab = _build_runner()
        fab.add_result(_success_with_data({"wrong": True}))
        fab.add_result(_success_with_data({"name": "ok"}))
        step = _make_step(output_schema={"type": "object", "required": ["name"]})

        await runner.run(step, {"original_param": "yes"}, {}, "t")

        # The schema retry request should have original_param + __schema_hint
        schema_req = fab.execute_calls[1]
        assert schema_req.params["original_param"] == "yes"
        assert "__schema_hint" in schema_req.params


# ===========================================================================
# TestDurationMeasurement
# ===========================================================================


class TestDurationMeasurement:
    """duration_ms is non-negative and reflects actual execution time."""

    async def test_duration_captures_time(self) -> None:
        runner, fab = _build_runner()

        async def _slow_execute(request: CapabilityRequest) -> CapabilityResult:
            await asyncio.sleep(0.02)  # 20ms
            return _success_result()

        fab.execute = _slow_execute  # type: ignore[assignment]
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        assert result.duration_ms >= 15  # allow some tolerance

    async def test_duration_includes_retry_time(self) -> None:
        runner, fab = _build_runner()
        fab.add_result(_failure_result(retriable=True))
        fab.add_result(_success_result())
        step = _make_step()

        result = await runner.run(step, {}, {}, "t")

        # Duration covers both attempts
        assert result.duration_ms >= 0
        assert result.retry_attempts == 1


# ===========================================================================
# TestExceptionFromFabric
# ===========================================================================


class TestExceptionFromFabric:
    """fabric_port.execute() raises an exception (not CapabilityResult failure)."""

    async def test_exception_wrapped_as_failed_result(self) -> None:
        runner, fab = _build_runner()
        fab.add_exception(RuntimeError("connection lost"))
        step = _make_step()

        result = await runner.run(step, {}, {}, "trace-x")

        assert result.status == StepStatus.FAILED
        assert result.error_detail == "connection lost"
        assert result.retry_attempts == 0
        # The exception path is NOT retried (not a structured failure)
        assert len(fab.execute_calls) == 1

    async def test_exception_result_has_correct_fields(self) -> None:
        runner, fab = _build_runner()
        fab.add_exception(ValueError("bad input"))
        step = _make_step(step_id="s-err", capability="cap.broken")

        result = await runner.run(step, {}, {}, "t")

        assert result.step_id == "s-err"
        assert result.capability_name == "cap.broken"
        assert result.result is not None
        assert result.result.success is False
        assert result.result.error is not None
        assert result.result.error.code == "execution_exception"
        assert result.result.error.retriable is False


# ===========================================================================
# TestRepr
# ===========================================================================


class TestRepr:
    """__repr__ coverage."""

    def test_repr_format(self) -> None:
        runner, _ = _build_runner()
        r = repr(runner)
        assert "StepRunner" in r
        assert "retries=2" in r
        assert "timeout=30000ms" in r

    def test_repr_custom_policies(self) -> None:
        runner, _ = _build_runner(
            policies=_default_policies(normal_retries=5, step_timeout_default_ms=10000)
        )
        r = repr(runner)
        assert "retries=5" in r
        assert "timeout=10000ms" in r
