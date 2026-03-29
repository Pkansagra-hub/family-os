"""
k1.fabric.output_validation -- 3-Tier Output Validation Pipeline.

Epic 3.5: Validates all provider execution results before returning
to callers.

Pipeline: Structural -> Schema -> Semantic
  - Structural (3.5.1): required fields, well-formed, no truncation, size limits
  - Schema (3.5.2): JSON Schema validation against contract.output
  - Semantic (3.5.3): hallucination detection, belief consistency (agent/prompt only)
  - Fallback (3.5.4): REJECT / COERCE / ANNOTATE strategies
  - Pipeline (3.5.5): composite pipeline with short-circuit and configuration

Exports:
  -- Shared types --
  ValidationTier, ValidationSeverity, ValidationIssue, ValidationResult

  -- 3.5.1 StructuralValidator --
  StructuralValidator, StructuralValidatorConfig
  DEFAULT_MAX_DATA_BYTES, TRUNCATION_MARKERS

  -- 3.5.2 SchemaValidator --
  SchemaValidator, SchemaCompiler, SchemaCompilationError
  attempt_coercion

  -- 3.5.3 SemanticValidator --
  SemanticValidator, HallucinationDetector
  HallucinationDetectorConfig, HallucinationReport
  ISessionStateReader, SEMANTIC_PROVIDER_TYPES

  -- 3.5.4 ValidationFallback --
  ValidationFallback, FallbackAction, FallbackResult
  EventPort, EVENT_VALIDATION_FAILED

  -- 3.5.5 OutputValidationPipeline --
  OutputValidationPipeline, OutputValidationConfig, PipelineOutcome
"""

# -- 3.5.5 OutputValidationPipeline --
from .pipeline import OutputValidationConfig, OutputValidationPipeline, PipelineOutcome

# -- 3.5.2 SchemaValidator --
from .schema_validator import (
    SchemaCompilationError,
    SchemaCompiler,
    SchemaValidator,
    attempt_coercion,
)

# -- 3.5.3 SemanticValidator --
from .semantic_validator import (
    SEMANTIC_PROVIDER_TYPES,
    HallucinationDetector,
    HallucinationDetectorConfig,
    HallucinationReport,
    ISessionStateReader,
    SemanticValidator,
)

# -- Shared types (from structural_validator) --
from .structural_validator import (
    DEFAULT_MAX_DATA_BYTES,
    TRUNCATION_MARKERS,
    StructuralValidator,
    StructuralValidatorConfig,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    ValidationTier,
)

# -- 3.5.4 ValidationFallback --
from .validation_fallback import (
    EVENT_VALIDATION_FAILED,
    EventPort,
    FallbackAction,
    FallbackResult,
    ValidationFallback,
)

__all__ = [
    # Shared types
    "ValidationTier",
    "ValidationSeverity",
    "ValidationIssue",
    "ValidationResult",
    # 3.5.1
    "StructuralValidator",
    "StructuralValidatorConfig",
    "DEFAULT_MAX_DATA_BYTES",
    "TRUNCATION_MARKERS",
    # 3.5.2
    "SchemaValidator",
    "SchemaCompiler",
    "SchemaCompilationError",
    "attempt_coercion",
    # 3.5.3
    "SemanticValidator",
    "HallucinationDetector",
    "HallucinationDetectorConfig",
    "HallucinationReport",
    "ISessionStateReader",
    "SEMANTIC_PROVIDER_TYPES",
    # 3.5.4
    "ValidationFallback",
    "FallbackAction",
    "FallbackResult",
    "EventPort",
    "EVENT_VALIDATION_FAILED",
    # 3.5.5
    "OutputValidationPipeline",
    "OutputValidationConfig",
    "PipelineOutcome",
]
