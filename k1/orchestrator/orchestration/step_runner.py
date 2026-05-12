"""
StepRunner -- Single-step execution delegator (Issues 2.3.1, 2.3.2, 2.3.3).

Builds CapabilityRequest from PlanStep + resolved params, executes
via IFabricGatewayPort with retry policy, wraps result in StepResult.

Constructor: 3 deps injected by OrchestratorFactory (6.2.1 step 11).
Primary method: run() -- async, returns StepResult.

Retry policy (2.3.2):
  - Normal retries: up to policies.normal_retries (2) for retriable errors.
  - Schema retries: up to policies.schema_retries (1) for output schema
    validation failures (2.3.3).
  - Max 3 calls per step total (2 normal + 1 schema).
  - Retry delay: 0ms (immediate, per ORCH-06).

Schema validation (2.3.3):
  - If step.output_schema is set and result.success: validate result.data
    against JSON Schema via jsonschema.validate.
  - If invalid and not yet schema_retried: build schema_hint string from
    errors, inject into params["__schema_hint"], and re-execute once.
  - Schema retry budget is separate from normal retries.
  - Only triggers for agent steps with structured output; most tool steps
    do not set output_schema.

Anti-hallucination:
  - StepRunner does NOT read from SessionState.
  - StepRunner does NOT call planner_port.
  - StepRunner does NOT write to WAL (that is DAGExecutor).
  - StepRunner does NOT resolve $-references (that is ParamResolver).
  - StepRunner does NOT handle saga compensation (that is DAGExecutor).
  - step.capability is already resolved by ParamResolver before run().
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

import jsonschema

from k1.fabric.types import CapabilityRequest, CapabilityResult, Tier
from k1.orchestrator.metrics import OrchestratorMetrics
from k1.orchestrator.types import (
    OrchestratorPolicies,
    SchemaResult,
    StepResult,
    StepStatus,
)

if TYPE_CHECKING:
    from k1.orchestrator.orchestration.error_router import ErrorRouter
    from k1.orchestrator.ports.fabric_gateway_port import IFabricGatewayPort
    from k1.orchestrator.types import PlanStep

log = logging.getLogger(__name__)


def _now_ms() -> int:
    """Return current monotonic time in milliseconds."""
    return int(time.monotonic() * 1000)


class StepRunner:
    """Single-step execution delegator with retry policy.

    Constructor: 3 deps (fabric_port, error_router, policies).
    run()               -- async, builds request + retry loop + wrap result.
    _execute_with_retry -- internal retry state machine.
    _build_request      -- builds CapabilityRequest from PlanStep.

    Stateless: no mutable internal state across run() invocations.
    """

    __slots__ = ("_fabric_port", "_error_router", "_policies", "_metrics")

    def __init__(
        self,
        fabric_port: IFabricGatewayPort,
        error_router: ErrorRouter,
        policies: OrchestratorPolicies,
        metrics: OrchestratorMetrics | None = None,
    ) -> None:
        """Construct StepRunner with 3 deps.

        Args:
            fabric_port: For execute() calls per step.
            error_router: For classifying Fabric errors (future use).
            policies: Retry limits and timeout defaults from
                      policies.contract.yaml (1.3.3).
        """
        self._fabric_port = fabric_port
        self._error_router = error_router
        self._policies = policies
        self._metrics = metrics or OrchestratorMetrics(enabled=False)

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    async def run(
        self,
        step: PlanStep,
        resolved_params: Dict[str, Any],
        prior_results: Dict[str, CapabilityResult],
        trace_id: str,
    ) -> StepResult:
        """Execute a single step via Fabric with retry policy.

        Logic:
          1. Build CapabilityRequest from PlanStep + resolved_params.
          2. Execute with retry loop (_execute_with_retry).
          3. Wrap CapabilityResult into StepResult.

        Args:
            step: PlanStep with capability, params, timeout, etc.
                  capability is already resolved (no $-refs).
            resolved_params: Params with $-references resolved by
                             ParamResolver. Overrides step.params.
            prior_results: Completed step results (step_id -> CapabilityResult).
                           Available for future retry context but not used in V1.
            trace_id: Cognitive trace ID for correlation.

        Returns:
            StepResult with COMPLETED or FAILED status, retry metadata.
        """
        with self._metrics.time_step_execution(
            step_id=step.id,
            capability_name=step.capability,
        ):
            step_start_ms = _now_ms()

            # Step 1: Build CapabilityRequest
            request = self._build_request(step, resolved_params, trace_id)

            # Step 2: Execute with retry
            result, retry_count, schema_retried = await self._execute_with_retry(
                request,
                step,
            )

            step_duration_ms = _now_ms() - step_start_ms

            # Step 3: Wrap in StepResult
            if result.success:
                return StepResult(
                    step_id=step.id,
                    capability_name=step.capability,
                    status=StepStatus.COMPLETED,
                    duration_ms=step_duration_ms,
                    result=result,
                    retry_attempts=retry_count,
                    schema_retry=schema_retried,
                )

            error_detail = result.error.message if result.error else "Unknown failure"
            return StepResult(
                step_id=step.id,
                capability_name=step.capability,
                status=StepStatus.FAILED,
                duration_ms=step_duration_ms,
                result=result,
                retry_attempts=retry_count,
                schema_retry=schema_retried,
                error_detail=error_detail,
            )

    # ------------------------------------------------------------------
    # Request builder
    # ------------------------------------------------------------------

    def _build_request(
        self,
        step: PlanStep,
        resolved_params: Dict[str, Any],
        trace_id: str,
    ) -> CapabilityRequest:
        """Build CapabilityRequest from PlanStep and resolved params.

        Timeout uses step.timeout_ms if set, else policies.step_timeout_default_ms.
        tools_granted passed via context_override (CapabilityRequest has no
        dedicated field; Fabric ContextBuilder extracts from context_override).

        Args:
            step: PlanStep with capability definition.
            resolved_params: Resolved params (overrides step.params).
            trace_id: Cognitive trace ID.

        Returns:
            CapabilityRequest ready for fabric_port.execute().
        """
        timeout_ms = step.timeout_ms or self._policies.step_timeout_default_ms

        context_override = None
        if step.tools_granted:
            context_override = {"tools_granted": list(step.tools_granted)}

        # Propagate PlanStep.safety_band_min to the CapabilityRequest so the
        # Fabric resolver permits providers whose minimum band exceeds GREEN.
        # Without this, every step request defaults to GREEN even when the
        # plan explicitly declared a higher band, causing band_denied errors.
        request_kwargs: Dict[str, Any] = {
            "capability_name": step.capability,
            "params": dict(resolved_params),
            "prompt_template": step.prompt_template,
            "tier": Tier.HIGH.value,
            "caller": "orchestrator",
            "caller_id": step.id,
            "trace_id": trace_id,
            "plan_id": step.id,
            "step_id": step.id,
            "timeout_ms": timeout_ms,
            "context_override": context_override,
        }
        if step.safety_band_min:
            request_kwargs["safety_band"] = step.safety_band_min

        return CapabilityRequest(**request_kwargs)

    # ------------------------------------------------------------------
    # Schema validation (2.3.3)
    # ------------------------------------------------------------------

    def validate_output_schema(
        self,
        result: CapabilityResult,
        schema: Dict[str, Any],
    ) -> SchemaResult:
        """Validate result.data against step.output_schema (JSON Schema).

        Uses jsonschema.validate (Draft 2020-12 compatible via
        jsonschema >= 4.20). Returns SchemaResult with errors list
        and human-readable suggestion for schema retry.

        Only called when step.output_schema is not None and the
        Fabric call returned success (result.success is True).

        Args:
            result: Successful CapabilityResult from Fabric.
            schema: JSON Schema dict from PlanStep.output_schema.

        Returns:
            SchemaResult(valid=True) if data matches schema.
            SchemaResult(valid=False, errors=[...], suggestion=...)
            if validation fails.
        """
        data = result.data
        if data is None:
            return SchemaResult(
                valid=False,
                errors=["result.data is None, expected object matching schema"],
                suggestion="Output data is missing; expected structured output.",
            )

        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError:
            # Collect all errors for multi-error schemas
            validator = jsonschema.Draft202012Validator(schema)
            all_errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
            errors = [e.message for e in all_errors] if all_errors else ["Unknown validation error"]
            suggestion = self._build_schema_suggestion(errors)
            return SchemaResult(
                valid=False,
                errors=errors,
                suggestion=suggestion,
            )
        except jsonschema.SchemaError as exc:
            # Malformed schema -- do not retry, just log and pass through
            log.warning(
                "[StepRunner] output_schema is invalid JSON Schema: %s",
                exc.message,
            )
            return SchemaResult(valid=True)

        return SchemaResult(valid=True)

    @staticmethod
    def _build_schema_suggestion(errors: List[str]) -> str:
        """Build human-readable schema_hint from validation errors."""
        if len(errors) == 1:
            return f"Output schema violation: {errors[0]}"
        parts = "; ".join(errors[:5])  # cap at 5 errors
        suffix = f" (and {len(errors) - 5} more)" if len(errors) > 5 else ""
        return f"Output schema violations: {parts}{suffix}"

    def _build_schema_retry_request(
        self,
        original_request: CapabilityRequest,
        step: PlanStep,
        schema_result: SchemaResult,
    ) -> CapabilityRequest:
        """Build a new CapabilityRequest with __schema_hint injected.

        Creates a copy of the original request with
        params["__schema_hint"] set to the human-readable suggestion.
        Fabric ContextBuilder extracts this reserved key.

        Args:
            original_request: The request that produced invalid output.
            step: PlanStep (for logging context).
            schema_result: SchemaResult with suggestion string.

        Returns:
            New CapabilityRequest with schema_hint in params.
        """
        hint = schema_result.suggestion or "Output did not match expected schema."
        new_params = dict(original_request.params)
        new_params["__schema_hint"] = hint
        log.info(
            "[StepRunner] Schema retry for step %s: %s",
            step.id,
            hint,
        )
        return replace(original_request, params=new_params)

    # ------------------------------------------------------------------
    # Retry state machine (2.3.2)
    # ------------------------------------------------------------------

    async def _execute_with_retry(
        self,
        request: CapabilityRequest,
        step: PlanStep,
    ) -> Tuple[CapabilityResult, int, bool]:
        """Execute request with retry policy.

        State machine:
          normal_attempts = 0, schema_retried = False.
          Loop:
            1. Execute via fabric_port.
            2. If success and step has output_schema -> validate.
               If valid -> return.
               If invalid and not schema_retried -> schema retry.
            3. If success and no output_schema -> return.
            4. If failure and retriable and under budget -> normal retry.
            5. Else -> return result as-is (FAILED or COMPLETED).

        Max calls per step: 1 initial + normal_retries + schema_retries
        = 1 + 2 + 1 = 4 max (but typically 1).

        Retry delay: 0ms (immediate, per ORCH-06).

        Args:
            request: CapabilityRequest to execute.
            step: PlanStep for schema validation context.

        Returns:
            (CapabilityResult, normal_retry_count, schema_retried).
        """
        normal_attempts = 0
        schema_retried = False
        max_normal = self._policies.normal_retries
        max_schema = self._policies.schema_retries
        current_request = request

        while True:
            try:
                # M5.1.1: enforce step-level timeout at the orchestrator
                # boundary so a hung Fabric call cannot stall the wave.
                # Step-specific timeout if set, else policy default.
                effective_timeout_ms = (
                    step.timeout_ms
                    if step.timeout_ms and step.timeout_ms > 0
                    else self._policies.step_timeout_default_ms
                )
                timeout_seconds = effective_timeout_ms / 1000.0
                with self._metrics.time_adapter_wait(adapter="fabric", operation="execute"):
                    result = await asyncio.wait_for(
                        self._fabric_port.execute(current_request),
                        timeout=timeout_seconds,
                    )
            except asyncio.TimeoutError:
                # Map orchestrator-side timeout to a structured failure.
                log.warning(
                    "[StepRunner] step %s exceeded timeout=%dms",
                    step.id,
                    effective_timeout_ms,
                )
                self._metrics.increment_step_retry(reason="timeout")
                # Treat as retriable up to the normal retry budget.
                if normal_attempts < max_normal:
                    normal_attempts += 1
                    current_request = request
                    continue
                return (
                    CapabilityResult.failure_result(
                        request_id=current_request.request_id,
                        error_code="step_timeout",
                        error_message=(
                            f"Step {step.id} exceeded timeout " f"{effective_timeout_ms}ms"
                        ),
                        retriable=False,
                        trace_id=current_request.trace_id,
                    ),
                    normal_attempts,
                    schema_retried,
                )
            except asyncio.CancelledError:
                # M5.1.2: cooperative cancellation surfaced from adapter.
                log.info(
                    "[StepRunner] step %s cancelled cooperatively",
                    step.id,
                )
                return (
                    CapabilityResult.failure_result(
                        request_id=current_request.request_id,
                        error_code="step_cancelled",
                        error_message=f"Step {step.id} cancelled",
                        retriable=False,
                        trace_id=current_request.trace_id,
                    ),
                    normal_attempts,
                    schema_retried,
                )
            except Exception as exc:
                # Fabric execution raised an exception (not a structured
                # CapabilityResult failure). Wrap as failure result.
                log.error(
                    "[StepRunner] fabric_port.execute raised for step %s: %s",
                    step.id,
                    exc,
                )
                return (
                    CapabilityResult.failure_result(
                        request_id=current_request.request_id,
                        error_code="execution_exception",
                        error_message=str(exc),
                        retriable=False,
                        trace_id=current_request.trace_id,
                    ),
                    normal_attempts,
                    schema_retried,
                )

            if result.success:
                # Schema validation (2.3.3): only if output_schema is set
                if step.output_schema:
                    sv = self.validate_output_schema(result, step.output_schema)
                    if not sv.valid:
                        # Schema validation failed -- can we retry?
                        schema_retries_done = 1 if schema_retried else 0
                        if schema_retries_done < max_schema:
                            schema_retried = True
                            self._metrics.increment_step_retry(reason="schema")
                            current_request = self._build_schema_retry_request(
                                request,
                                step,
                                sv,
                            )
                            continue
                        # Budget exhausted -- return as-is (still success from Fabric)
                        log.info(
                            "[StepRunner] Schema validation failed for step %s "
                            "but schema retry budget exhausted: %s",
                            step.id,
                            sv.suggestion,
                        )
                return (result, normal_attempts, schema_retried)

            # Failure path: check if retriable
            is_retriable = result.error is not None and result.error.retriable

            if is_retriable and normal_attempts < max_normal:
                normal_attempts += 1
                self._metrics.increment_step_retry(reason="transient")
                log.info(
                    "[StepRunner] Retrying step %s (attempt %d/%d): %s",
                    step.id,
                    normal_attempts,
                    max_normal,
                    result.error.message if result.error else "unknown",
                )
                current_request = request  # reset to original (no schema hint)
                continue

            # Not retriable or budget exhausted
            if normal_attempts > 0:
                log.info(
                    "[StepRunner] Step %s failed after %d retries: %s",
                    step.id,
                    normal_attempts,
                    result.error.message if result.error else "unknown",
                )

            return (result, normal_attempts, schema_retried)

    def __repr__(self) -> str:
        return (
            f"StepRunner(retries={self._policies.normal_retries}, "
            f"timeout={self._policies.step_timeout_default_ms}ms)"
        )
