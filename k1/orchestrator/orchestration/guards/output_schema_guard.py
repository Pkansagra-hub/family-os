"""
k1.orchestrator.orchestration.guards.output_schema_guard -- ORCH-15.

Post-step guard that validates step output against JSON Schema.
Triggers schema retry on first validation failure, FAIL on second.

Guard pipeline position: G9 (post-step).

Design:
  - Stateless: no constructor state, no instance caching.
  - Uses jsonschema.validate() with Draft 2020-12.
  - format_checker=None to avoid slow format validation on large payloads.
  - schema_retry field on StepResult indicates if schema retry already occurred.

Decision matrix:
  output_schema is None         -> BYPASS (no schema defined)
  result.status != COMPLETED    -> CONTINUE (step already failed, not our concern)
  result.data is None           -> RETRY/FAIL (expected output but got nothing)
  schema valid                  -> CONTINUE (proceed to param resolution)
  schema invalid + first try    -> RETRY (StepRunner re-invokes with __schema_hint)
  schema invalid + retried      -> FAIL (step marked FAILED, cancel_dependents)

References:
  - orchestrator-implementation-plan.md Issue 3.2.1
  - Schema Whiteboard Section 8 (G9=OutputSchemaGuard)
  - StepRunner._build_schema_retry_request() (2.3.3)

Exports:
  OutputSchemaGuard
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import jsonschema

from k1.orchestrator.types import (
    GuardAction,
    GuardDecision,
    PlanStep,
    ProcessingContext,
    StepResult,
    StepStatus,
)

from .base import DAGGuard

logger = logging.getLogger(__name__)

# Guard identity constant
_GUARD_NAME = "OutputSchemaGuard"


def _validate_schema(
    data: Optional[Dict[str, Any]],
    schema: Dict[str, Any],
) -> Optional[str]:
    """Validate data against JSON Schema (Draft 2020-12).

    Args:
        data: Step output data to validate.
        schema: JSON Schema dict to validate against.

    Returns:
        None if valid, human-readable error message if invalid.
    """
    if data is None:
        return "Step produced no output data but output_schema is defined"

    try:
        jsonschema.validate(
            instance=data,
            schema=schema,
            format_checker=None,  # Skip format checks for performance
        )
        return None
    except jsonschema.ValidationError as exc:
        # Build a concise but informative error message
        path = ".".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "(root)"
        return f"Schema validation failed at '{path}': {exc.message}"
    except jsonschema.SchemaError as exc:
        # The schema itself is malformed -- treat as guard error, not step error
        logger.error(
            "[%s] Malformed output_schema for step: %s",
            _GUARD_NAME,
            exc.message,
        )
        return f"Malformed output_schema: {exc.message}"


class OutputSchemaGuard(DAGGuard):
    """Post-step guard for JSON Schema output validation (ORCH-15).

    Validates step result.data against step.output_schema when present.
    Stateless -- no constructor dependencies.

    Decision flow:
      1. No output_schema -> BYPASS (guard not applicable)
      2. Step not COMPLETED (failed/cancelled/skipped) -> CONTINUE (not our job)
      3. Validate result.data against schema
      4. Valid -> CONTINUE
      5. Invalid + first attempt (schema_retry=False) -> RETRY
      6. Invalid + already retried (schema_retry=True) -> HARD_STOP

    Metadata on RETRY/HARD_STOP:
      validation_error: human-readable schema validation message
    """

    async def after_step(
        self,
        step: PlanStep,
        result: StepResult,
        ctx: ProcessingContext,
    ) -> GuardDecision:
        """Validate step output against JSON Schema.

        Args:
            step: PlanStep with optional output_schema.
            result: StepResult from step execution.
            ctx: ProcessingContext for trace correlation.

        Returns:
            GuardDecision with action BYPASS, CONTINUE, RETRY, or HARD_STOP.
        """
        # 1. No schema defined -> guard not applicable
        if step.output_schema is None:
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.BYPASS,
                reason="No output_schema defined for step",
            )

        # 2. Step already failed -> not our concern
        if result.status != StepStatus.COMPLETED:
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason="Step already failed; schema validation skipped",
            )

        # 3. Validate result data against schema
        data = result.result.data if result.result else None
        error_msg = _validate_schema(data, step.output_schema)

        # 4. Schema valid -> proceed
        if error_msg is None:
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason="Output matches schema",
            )

        # 5. Schema invalid: check if already retried
        if result.schema_retry:
            # Already used the schema retry -> HARD_STOP (step fails)
            logger.warning(
                "[%s] Schema validation failed after retry for step '%s': %s",
                _GUARD_NAME,
                step.id,
                error_msg,
            )
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.HARD_STOP,
                reason=f"Schema validation failed after retry: {error_msg}",
                metadata={"validation_error": error_msg},
            )

        # 6. First schema failure -> RETRY with hint
        logger.info(
            "[%s] Schema validation failed for step '%s', requesting retry: %s",
            _GUARD_NAME,
            step.id,
            error_msg,
        )
        return GuardDecision(
            guard_name=_GUARD_NAME,
            action=GuardAction.RETRY,
            reason=f"Schema validation failed: {error_msg}",
            metadata={"validation_error": error_msg},
        )

    def __repr__(self) -> str:
        return "OutputSchemaGuard()"
