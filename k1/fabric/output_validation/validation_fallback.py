"""
k1.fabric.output_validation.validation_fallback -- Tier Failure Handling.

Issue 3.5.4 -- ValidationFallback.

Determines the action when a validation tier fails:
  - Structural fail: REJECT immediately (return CapabilityResult.failure).
  - Schema fail: attempt coercion, re-validate, if still fails REJECT.
  - Semantic fail: annotate result with low-confidence warning, do NOT reject.

Emits ``k1.fabric.output.validation.failed.v1`` on any rejection via EventPort.

Dependencies:
  - schema_validator.attempt_coercion() for schema coercion.
  - EventPort protocol for failure event emission.

References:
  - fabric-implementation-plan.md Issue 3.5.4
  - Epic 3.5 wiring: emits via IEventPort (5.1.2)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from .schema_validator import SchemaValidator, _validate_against_schema, attempt_coercion
from .structural_validator import ValidationIssue, ValidationResult, ValidationTier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event constants
# ---------------------------------------------------------------------------

EVENT_VALIDATION_FAILED = "k1.fabric.output.validation.failed.v1"


# ---------------------------------------------------------------------------
# EventPort protocol (structural subtype -- matches core/registry.py)
# ---------------------------------------------------------------------------


class EventPort(Protocol):
    """Minimal protocol for event emission."""

    def emit(self, event_type: str, payload: Any) -> None:
        """Emit an event to the bus."""
        ...


# ---------------------------------------------------------------------------
# Fallback action enum
# ---------------------------------------------------------------------------


class FallbackAction:
    """Constants for fallback outcomes."""

    REJECT = "REJECT"
    COERCE = "COERCE"
    ANNOTATE = "ANNOTATE"
    PASS = "PASS"


# ---------------------------------------------------------------------------
# FallbackResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FallbackResult:
    """
    Outcome of the fallback handler.

    Attributes:
        action: What action was taken (REJECT, COERCE, ANNOTATE, PASS).
        rejected: True if the result should be rejected (caller returns failure).
        coerced_data: If action=COERCE and coercion succeeded, the fixed data.
        annotations: Warnings to attach to the result (for ANNOTATE action).
        issues: All validation issues that led to this fallback.
        event_emitted: Whether a failure event was emitted.
    """

    action: str
    rejected: bool
    coerced_data: Optional[Dict[str, Any]] = None
    annotations: List[str] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    event_emitted: bool = False


# ---------------------------------------------------------------------------
# 3.5.4 -- ValidationFallback
# ---------------------------------------------------------------------------


class ValidationFallback:
    """
    Handles validation failures based on tier and severity.

    Strategies:
      STRUCTURAL (HARD) -> immediate REJECT
      SCHEMA (HARD)     -> attempt coercion -> re-validate -> REJECT if still fails
      SEMANTIC (SOFT)    -> ANNOTATE with warning (never reject)

    Thread-safe.  Stateless except for the optional event_port.

    Usage::

        fallback = ValidationFallback(event_port=bus)
        result = fallback.handle(validation_result, original_data, contract)
        if result.rejected:
            return CapabilityResult.failure_result(...)
    """

    __slots__ = ("_event_port", "_schema_validator")

    def __init__(
        self,
        event_port: Optional[EventPort] = None,
        schema_validator: Optional[SchemaValidator] = None,
    ) -> None:
        self._event_port = event_port
        self._schema_validator = schema_validator

    def handle(
        self,
        validation_result: ValidationResult,
        original_data: Optional[Dict[str, Any]] = None,
        contract: Any = None,
        request_id: str = "",
        provider_id: str = "",
        trace_id: str = "",
    ) -> FallbackResult:
        """
        Determine fallback action for a failed validation result.

        Args:
            validation_result: The failed ValidationResult.
            original_data: The original result.data (for schema coercion).
            contract: The CapabilityContract (for schema coercion).
            request_id: Request ID for event payload.
            provider_id: Provider ID for event payload.
            trace_id: Trace ID for event payload.

        Returns:
            FallbackResult describing the action taken.
        """
        # If valid, nothing to do
        if validation_result.valid:
            return FallbackResult(
                action=FallbackAction.PASS,
                rejected=False,
            )

        tier = validation_result.tier

        if tier == ValidationTier.STRUCTURAL:
            return self._handle_structural(validation_result, request_id, provider_id, trace_id)
        elif tier == ValidationTier.SCHEMA:
            return self._handle_schema(
                validation_result,
                original_data,
                contract,
                request_id,
                provider_id,
                trace_id,
            )
        elif tier == ValidationTier.SEMANTIC:
            return self._handle_semantic(validation_result)
        else:
            # Unknown tier -- reject to be safe
            self._emit_failure_event(
                tier="UNKNOWN",
                issues=validation_result.issues,
                request_id=request_id,
                provider_id=provider_id,
                trace_id=trace_id,
            )
            return FallbackResult(
                action=FallbackAction.REJECT,
                rejected=True,
                issues=list(validation_result.issues),
                event_emitted=True,
            )

    # ---- tier handlers -----------------------------------------------------

    def _handle_structural(
        self,
        result: ValidationResult,
        request_id: str,
        provider_id: str,
        trace_id: str,
    ) -> FallbackResult:
        """Structural fail: immediate REJECT."""
        emitted = self._emit_failure_event(
            tier="STRUCTURAL",
            issues=result.issues,
            request_id=request_id,
            provider_id=provider_id,
            trace_id=trace_id,
        )
        return FallbackResult(
            action=FallbackAction.REJECT,
            rejected=True,
            issues=list(result.issues),
            event_emitted=emitted,
        )

    def _handle_schema(
        self,
        result: ValidationResult,
        original_data: Optional[Dict[str, Any]],
        contract: Any,
        request_id: str,
        provider_id: str,
        trace_id: str,
    ) -> FallbackResult:
        """Schema fail: attempt coercion, re-validate, or REJECT."""
        output_schema = getattr(contract, "output", None) if contract else None

        # If we have data and a schema, attempt coercion
        if original_data is not None and output_schema:
            coerced_data, fixes = attempt_coercion(original_data, output_schema)

            if fixes:
                # Re-validate coerced data
                re_errors = _validate_against_schema(coerced_data, output_schema)

                if not re_errors:
                    # Coercion succeeded
                    logger.info(
                        "Schema coercion succeeded for request %s: %s",
                        request_id,
                        "; ".join(fixes),
                    )
                    return FallbackResult(
                        action=FallbackAction.COERCE,
                        rejected=False,
                        coerced_data=coerced_data,
                        annotations=[f"Coercion applied: {f}" for f in fixes],
                        issues=list(result.issues),
                        event_emitted=False,
                    )

        # Coercion failed or not possible: REJECT
        emitted = self._emit_failure_event(
            tier="SCHEMA",
            issues=result.issues,
            request_id=request_id,
            provider_id=provider_id,
            trace_id=trace_id,
        )
        return FallbackResult(
            action=FallbackAction.REJECT,
            rejected=True,
            issues=list(result.issues),
            event_emitted=emitted,
        )

    def _handle_semantic(self, result: ValidationResult) -> FallbackResult:
        """Semantic fail: ANNOTATE with warnings, never reject."""
        annotations = [f"[semantic] {iss.message}" for iss in result.issues]
        annotations.append(f"[semantic] confidence={result.confidence:.2f}")

        return FallbackResult(
            action=FallbackAction.ANNOTATE,
            rejected=False,
            annotations=annotations,
            issues=list(result.issues),
            event_emitted=False,
        )

    # ---- event emission ----------------------------------------------------

    def _emit_failure_event(
        self,
        tier: str,
        issues: List[ValidationIssue],
        request_id: str,
        provider_id: str,
        trace_id: str,
    ) -> bool:
        """
        Emit validation failure event.  Returns True if emitted.
        """
        if self._event_port is None:
            return False

        payload: Dict[str, Any] = {
            "tier": tier,
            "request_id": request_id,
            "provider_id": provider_id,
            "trace_id": trace_id,
            "issues": [
                {
                    "code": iss.code,
                    "message": iss.message,
                    "severity": (
                        iss.severity.value if hasattr(iss.severity, "value") else str(iss.severity)
                    ),
                }
                for iss in issues
            ],
        }

        try:
            self._event_port.emit(EVENT_VALIDATION_FAILED, payload)
            return True
        except Exception:
            logger.warning("Failed to emit %s event", EVENT_VALIDATION_FAILED, exc_info=True)
            return False
