"""
k1.fabric.output_validation.pipeline -- Composite Output Validation Pipeline.

Issue 3.5.5 -- OutputValidationPipeline.

Runs the 3-tier validation pipeline in sequence:
  Structural -> Schema -> Semantic

Short-circuits on hard failure (Structural, Schema).
Passes through on soft failure (Semantic warning).
Configurable: ``skip_semantic=True`` for tool-only results.

Wired into FabricFacade.execute() (5.3.2) AFTER provider.execute()
returns and BEFORE returning CapabilityResult to caller.

Dependencies:
  - StructuralValidator (3.5.1)
  - SchemaValidator (3.5.2) + SchemaCompiler
  - SemanticValidator (3.5.3)
  - ValidationFallback (3.5.4)

References:
  - fabric-implementation-plan.md Issue 3.5.5
  - Epic 3.5 wiring: Provider result -> Structural -> Schema -> Semantic -> return
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schema_validator import SchemaCompiler, SchemaValidator
from .semantic_validator import (
    SEMANTIC_PROVIDER_TYPES,
    HallucinationDetectorConfig,
    ISessionStateReader,
    SemanticValidator,
)
from .structural_validator import StructuralValidator, StructuralValidatorConfig, ValidationResult
from .validation_fallback import EventPort, FallbackResult, ValidationFallback

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutputValidationConfig:
    """
    Configuration for the OutputValidationPipeline.

    Attributes:
        skip_semantic: When True, skip semantic validation entirely.
        structural_config: Config for StructuralValidator.
        hallucination_config: Config for HallucinationDetector.
        enable_coercion: Whether to attempt coercion on schema failures.
    """

    skip_semantic: bool = False
    structural_config: Optional[StructuralValidatorConfig] = None
    hallucination_config: Optional[HallucinationDetectorConfig] = None
    enable_coercion: bool = True


# ---------------------------------------------------------------------------
# Pipeline outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineOutcome:
    """
    Full outcome from the OutputValidationPipeline.

    Attributes:
        passed: True if the result passed all tiers (or soft-failed semantic).
        rejected: True if the result was rejected by a hard failure.
        tier_results: List of ValidationResults from each tier that ran.
        fallback_result: FallbackResult if fallback was invoked (None otherwise).
        coerced_data: If coercion was applied, the fixed data dict.
        annotations: Warnings/annotations collected (from semantic + coercion).
        rejection_reason: Human-readable rejection reason (empty when passed).
    """

    passed: bool
    rejected: bool
    tier_results: List[ValidationResult] = field(default_factory=list)
    fallback_result: Optional[FallbackResult] = None
    coerced_data: Optional[Dict[str, Any]] = None
    annotations: List[str] = field(default_factory=list)
    rejection_reason: str = ""


# ---------------------------------------------------------------------------
# 3.5.5 -- OutputValidationPipeline
# ---------------------------------------------------------------------------


class OutputValidationPipeline:
    """
    Composite 3-tier output validation pipeline.

    Pipeline flow:
      1. StructuralValidator -- hard fail on malformed results.
      2. SchemaValidator -- hard fail on schema violations (with coercion).
      3. SemanticValidator -- soft fail (annotate, never reject).

    Short-circuits on hard failure.  Soft failures are annotated and
    passed through.

    Constructed by FabricFactory (5.3.1) with injected ports:
      - state_reader: ISessionStateReader for semantic checks
      - event_port: EventPort for failure event emission

    Usage::

        pipeline = OutputValidationPipeline(
            state_reader=reader,
            event_port=bus,
            config=OutputValidationConfig(skip_semantic=True),
        )

        outcome = pipeline.validate(
            result=capability_result,
            contract=contract,
            provider_type="MCP",
        )

        if outcome.rejected:
            return CapabilityResult.failure_result(
                request_id=...,
                error_code="output_validation_failed",
                error_message=outcome.rejection_reason,
            )
    """

    __slots__ = (
        "_structural",
        "_schema",
        "_semantic",
        "_fallback",
        "_config",
    )

    def __init__(
        self,
        state_reader: Optional[ISessionStateReader] = None,
        event_port: Optional[EventPort] = None,
        config: Optional[OutputValidationConfig] = None,
        schema_compiler: Optional[SchemaCompiler] = None,
    ) -> None:
        self._config = config or OutputValidationConfig()

        self._structural = StructuralValidator(config=self._config.structural_config)
        compiler = schema_compiler or SchemaCompiler()
        self._schema = SchemaValidator(compiler=compiler)
        self._semantic = SemanticValidator(
            state_reader=state_reader,
            config=self._config.hallucination_config,
        )
        self._fallback = ValidationFallback(
            event_port=event_port,
            schema_validator=self._schema,
        )

    # ---- public properties -------------------------------------------------

    @property
    def structural_validator(self) -> StructuralValidator:
        """Access the StructuralValidator (for testing/inspection)."""
        return self._structural

    @property
    def schema_validator(self) -> SchemaValidator:
        """Access the SchemaValidator (for testing/inspection)."""
        return self._schema

    @property
    def semantic_validator(self) -> SemanticValidator:
        """Access the SemanticValidator (for testing/inspection)."""
        return self._semantic

    @property
    def fallback(self) -> ValidationFallback:
        """Access the ValidationFallback (for testing/inspection)."""
        return self._fallback

    @property
    def config(self) -> OutputValidationConfig:
        """Access the pipeline configuration."""
        return self._config

    # ---- main API ----------------------------------------------------------

    def validate(
        self,
        result: Any,
        contract: Any = None,
        provider_type: str = "",
        session_id: Optional[str] = None,
        execution_context: Optional[Dict[str, Any]] = None,
        request_id: str = "",
        provider_id: str = "",
        trace_id: str = "",
    ) -> PipelineOutcome:
        """
        Run the full validation pipeline on a CapabilityResult.

        Args:
            result: The CapabilityResult to validate.
            contract: CapabilityContract for schema validation.
            provider_type: Provider type string (for semantic tier gating).
            session_id: Session ID for belief consistency checks.
            execution_context: Context provided to the agent/provider.
            request_id: For event payloads.
            provider_id: For event payloads.
            trace_id: For event payloads.

        Returns:
            PipelineOutcome with full validation details.
        """
        tier_results: List[ValidationResult] = []
        annotations: List[str] = []
        coerced_data: Optional[Dict[str, Any]] = None

        # ----- Tier 1: Structural -----
        structural_result = self._structural.validate(result)
        tier_results.append(structural_result)

        if not structural_result.valid:
            fb = self._fallback.handle(
                structural_result,
                request_id=request_id,
                provider_id=provider_id,
                trace_id=trace_id,
            )
            reason = "; ".join(i.message for i in structural_result.issues)
            return PipelineOutcome(
                passed=False,
                rejected=True,
                tier_results=tier_results,
                fallback_result=fb,
                rejection_reason=f"Structural validation failed: {reason}",
            )

        # ----- Tier 2: Schema (only for success results with data) -----
        if getattr(result, "success", False) and getattr(result, "data", None) is not None:
            schema_result = self._schema.validate(result.data, contract)
            tier_results.append(schema_result)

            if not schema_result.valid:
                fb = self._fallback.handle(
                    schema_result,
                    original_data=result.data,
                    contract=contract,
                    request_id=request_id,
                    provider_id=provider_id,
                    trace_id=trace_id,
                )

                if fb.rejected:
                    reason = "; ".join(i.message for i in schema_result.issues)
                    return PipelineOutcome(
                        passed=False,
                        rejected=True,
                        tier_results=tier_results,
                        fallback_result=fb,
                        rejection_reason=f"Schema validation failed: {reason}",
                    )

                # Coercion succeeded
                if fb.coerced_data is not None:
                    coerced_data = fb.coerced_data
                    annotations.extend(fb.annotations)

        # ----- Tier 3: Semantic (optional) -----
        if (
            not self._config.skip_semantic
            and getattr(result, "success", False)
            and getattr(result, "data", None) is not None
            and provider_type in SEMANTIC_PROVIDER_TYPES
        ):
            data_to_check = coerced_data if coerced_data is not None else result.data
            semantic_result = self._semantic.validate(
                data=data_to_check,
                provider_type=provider_type,
                session_id=session_id,
                execution_context=execution_context,
            )
            tier_results.append(semantic_result)

            if not semantic_result.valid:
                fb = self._fallback.handle(semantic_result)
                annotations.extend(fb.annotations)

        # ----- All tiers passed (or soft-failed) -----
        return PipelineOutcome(
            passed=True,
            rejected=False,
            tier_results=tier_results,
            coerced_data=coerced_data,
            annotations=annotations,
        )

    # ---- convenience methods -----------------------------------------------

    def validate_quick(self, result: Any) -> bool:
        """
        Quick pass/fail check without full details.

        Runs structural validation only.  Useful for fast rejection
        of obviously malformed results.
        """
        return self._structural.validate(result).valid
