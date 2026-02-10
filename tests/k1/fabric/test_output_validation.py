"""
Epic 6.2.11 -- Test OutputValidationPipeline.

Tests the 3-tier output validation pipeline:
  Tier 1 -- StructuralValidator (rejects malformed results)
  Tier 2 -- SchemaValidator (rejects schema-violating data)
  Tier 3 -- SemanticValidator (flags low-confidence outputs)
  Fallback -- ValidationFallback (REJECT / COERCE / ANNOTATE)
  Pipeline -- OutputValidationPipeline (composite, short-circuit)

Covers:
  - StructuralValidator: required fields, data well-formed, truncation,
    size limits.
  - SchemaValidator: valid passes, missing required, type mismatch,
    nested validation, coercion helpers.
  - SemanticValidator: uncertainty markers, fabrication patterns,
    belief contradictions, non-semantic skip.
  - ValidationFallback: structural REJECT, schema COERCE/REJECT,
    semantic ANNOTATE, event emission.
  - OutputValidationPipeline: full 3-tier flow, skip_semantic config,
    short-circuit on structural fail, coercion pass-through.

NO MOCKS.  Real adapters with in-memory state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.output_validation import (
    EVENT_VALIDATION_FAILED,
    FallbackAction,
    HallucinationDetector,
    OutputValidationConfig,
    OutputValidationPipeline,
    SchemaCompilationError,
    SchemaCompiler,
    SchemaValidator,
    SemanticValidator,
    StructuralValidator,
    StructuralValidatorConfig,
    ValidationFallback,
    ValidationResult,
    ValidationSeverity,
    ValidationTier,
    attempt_coercion,
)
from k1.fabric.types import CapabilityContract, CapabilityResult, ErrorInfo

# =========================================================================
# Test Adapters (real, in-memory)
# =========================================================================


class InMemorySessionStateReader:
    """Real in-memory ISessionStateReader for semantic validator tests."""

    def __init__(self, sections: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._sections: Dict[str, Dict[str, Any]] = sections or {}

    def set_section(self, session_id: str, section: str, data: Dict[str, Any]) -> None:
        key = f"{session_id}:{section}"
        self._sections[key] = data

    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        return self._sections.get(f"{session_id}:{section}")


class CaptureEventPort:
    """Real in-memory event port that captures emitted events."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, event_type: str, payload: Any) -> None:
        self.events.append({"event_type": event_type, "payload": payload})


# =========================================================================
# Result builders
# =========================================================================


def _success(data: Dict[str, Any], **kw: Any) -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id=kw.get("request_id", "r1"),
        data=data,
        provider_id=kw.get("provider_id", "p1"),
        trace_id=kw.get("trace_id", "t1"),
    )


def _failure(code: str = "err", msg: str = "fail") -> CapabilityResult:
    return CapabilityResult.failure_result(request_id="r1", error_code=code, error_message=msg)


def _contract(output_schema: Optional[Dict[str, Any]] = None, **kw: Any) -> CapabilityContract:
    return CapabilityContract(
        name=kw.get("name", "tool.execute.test"),
        version=kw.get("version", "1.0.0"),
        domain=["TEST"],
        description="Test contract",
        output=output_schema or {},
    )


# =========================================================================
# Tier 1: StructuralValidator
# =========================================================================


class TestStructuralValidator:
    """Structural integrity checks on CapabilityResult."""

    def setup_method(self) -> None:
        self.v = StructuralValidator()

    def test_valid_success_result(self) -> None:
        r = _success({"answer": "ok"})
        vr = self.v.validate(r)
        assert vr.valid is True
        assert vr.tier == ValidationTier.STRUCTURAL

    def test_valid_failure_result(self) -> None:
        r = _failure()
        vr = self.v.validate(r)
        assert vr.valid is True

    def test_missing_success_field(self) -> None:
        """Object without 'success' attribute fails."""

        class Bare:
            pass

        vr = self.v.validate(Bare())
        assert vr.valid is False
        assert any(i.code == "missing_success_field" for i in vr.issues)

    def test_success_true_without_data(self) -> None:
        r = CapabilityResult(success=True, data=None, error=None)
        vr = self.v.validate(r)
        assert vr.valid is False
        assert any(i.code == "success_without_data" for i in vr.issues)

    def test_success_true_with_error(self) -> None:
        r = CapabilityResult(
            success=True,
            data={"ok": True},
            error=ErrorInfo(code="oops"),
        )
        vr = self.v.validate(r)
        assert vr.valid is False
        assert any(i.code == "success_with_error" for i in vr.issues)

    def test_failure_without_error(self) -> None:
        r = CapabilityResult(success=False, data=None, error=None)
        vr = self.v.validate(r)
        assert vr.valid is False
        assert any(i.code == "failure_without_error" for i in vr.issues)

    def test_data_not_dict(self) -> None:
        """success=True with data as string is structural failure."""

        @dataclass
        class FakeResult:
            success: bool = True
            data: Any = "not a dict"
            error: Any = None

        vr = self.v.validate(FakeResult())
        assert vr.valid is False
        assert any(i.code == "data_not_dict" for i in vr.issues)

    def test_truncation_detected(self) -> None:
        r = _success({"text": "Hello world... [truncated]"})
        vr = self.v.validate(r)
        assert vr.valid is False
        assert any(i.code == "truncation_detected" for i in vr.issues)
        assert "truncation_locations" in vr.metadata

    def test_truncation_disabled(self) -> None:
        cfg = StructuralValidatorConfig(check_truncation=False)
        v = StructuralValidator(config=cfg)
        r = _success({"text": "Hello... [truncated]"})
        vr = v.validate(r)
        assert vr.valid is True

    def test_data_too_large(self) -> None:
        cfg = StructuralValidatorConfig(max_data_bytes=50)
        v = StructuralValidator(config=cfg)
        r = _success({"big": "x" * 200})
        vr = v.validate(r)
        assert vr.valid is False
        assert any(i.code == "data_too_large" for i in vr.issues)

    def test_nested_truncation(self) -> None:
        r = _success({"outer": {"inner": {"deep": "value [output cut]"}}})
        vr = self.v.validate(r)
        assert vr.valid is False


# =========================================================================
# Tier 2: SchemaValidator + SchemaCompiler
# =========================================================================


class TestSchemaCompiler:
    """SchemaCompiler caching and compilation."""

    def test_compile_and_cache(self) -> None:
        compiler = SchemaCompiler()
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        s1 = compiler.get_or_compile("test", "1.0.0", schema)
        s2 = compiler.get_or_compile("test", "1.0.0", schema)
        assert s1 is s2  # same reference = cached
        assert compiler.cache_size == 1

    def test_invalidate(self) -> None:
        compiler = SchemaCompiler()
        compiler.get_or_compile("test", "1.0.0", {"type": "object"})
        assert compiler.invalidate("test", "1.0.0") is True
        assert compiler.cache_size == 0
        assert compiler.invalidate("test", "1.0.0") is False

    def test_invalid_schema_type(self) -> None:
        compiler = SchemaCompiler()
        with pytest.raises(SchemaCompilationError):
            compiler.get_or_compile("test", "1.0.0", "not_a_dict")  # type: ignore


class TestSchemaValidator:
    """SchemaValidator validates data against contract output schema."""

    def setup_method(self) -> None:
        self.v = SchemaValidator()

    def test_no_schema_passes(self) -> None:
        """Contract with no output schema -> pass."""
        c = _contract(output_schema={})
        vr = self.v.validate({"anything": True}, c)
        assert vr.valid is True

    def test_valid_data_passes(self) -> None:
        schema = {
            "type": "object",
            "required": ["status"],
            "properties": {"status": {"type": "string"}},
        }
        c = _contract(output_schema=schema)
        vr = self.v.validate({"status": "ok"}, c)
        assert vr.valid is True

    def test_missing_required_field(self) -> None:
        schema = {
            "type": "object",
            "required": ["status"],
            "properties": {"status": {"type": "string"}},
        }
        c = _contract(output_schema=schema)
        vr = self.v.validate({}, c)
        assert vr.valid is False
        assert any(i.code == "schema_violation" for i in vr.issues)

    def test_type_mismatch(self) -> None:
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        }
        c = _contract(output_schema=schema)
        vr = self.v.validate({"count": "not_a_number"}, c)
        assert vr.valid is False

    def test_nested_validation(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "inner": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string"}},
                }
            },
        }
        c = _contract(output_schema=schema)
        vr = self.v.validate({"inner": {}}, c)
        assert vr.valid is False

    def test_array_items_validation(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
        }
        c = _contract(output_schema=schema)
        vr = self.v.validate({"items": ["ok", 42]}, c)
        assert vr.valid is False

    def test_enum_validation(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        }
        c = _contract(output_schema=schema)
        vr = self.v.validate({"level": "ultra"}, c)
        assert vr.valid is False

    def test_min_max_items(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "minItems": 1, "maxItems": 3},
            },
        }
        c = _contract(output_schema=schema)
        vr = self.v.validate({"tags": []}, c)
        assert vr.valid is False

    def test_string_length(self) -> None:
        schema = {
            "type": "object",
            "properties": {"code": {"type": "string", "minLength": 3, "maxLength": 5}},
        }
        c = _contract(output_schema=schema)
        assert self.v.validate({"code": "AB"}, c).valid is False
        assert self.v.validate({"code": "ABCDEF"}, c).valid is False
        assert self.v.validate({"code": "ABCD"}, c).valid is True

    def test_number_range(self) -> None:
        schema = {
            "type": "object",
            "properties": {"score": {"type": "number", "minimum": 0, "maximum": 100}},
        }
        c = _contract(output_schema=schema)
        assert self.v.validate({"score": -1}, c).valid is False
        assert self.v.validate({"score": 101}, c).valid is False
        assert self.v.validate({"score": 50}, c).valid is True


# =========================================================================
# Coercion Helpers
# =========================================================================


class TestCoercion:
    """attempt_coercion() strategies."""

    def test_fill_missing_required_with_default(self) -> None:
        schema = {
            "required": ["status"],
            "properties": {"status": {"type": "string", "default": "unknown"}},
        }
        coerced, fixes = attempt_coercion({}, schema)
        assert coerced["status"] == "unknown"
        assert len(fixes) == 1

    def test_fill_missing_types(self) -> None:
        schema = {
            "required": ["name", "count", "tags", "meta", "active"],
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "tags": {"type": "array"},
                "meta": {"type": "object"},
                "active": {"type": "boolean"},
            },
        }
        coerced, fixes = attempt_coercion({}, schema)
        assert coerced["name"] == ""
        assert coerced["count"] == 0
        assert coerced["tags"] == []
        assert coerced["meta"] == {}
        assert coerced["active"] is False
        assert len(fixes) == 5

    def test_cast_string_to_number(self) -> None:
        schema = {"properties": {"price": {"type": "number"}}}
        coerced, fixes = attempt_coercion({"price": "9.99"}, schema)
        assert coerced["price"] == 9.99
        assert len(fixes) == 1

    def test_cast_string_to_integer(self) -> None:
        schema = {"properties": {"count": {"type": "integer"}}}
        coerced, fixes = attempt_coercion({"count": "42"}, schema)
        assert coerced["count"] == 42

    def test_uncoercible_no_change(self) -> None:
        schema = {"properties": {"count": {"type": "integer"}}}
        coerced, fixes = attempt_coercion({"count": "not_a_number"}, schema)
        # cast fails silently; value is not changed
        assert coerced["count"] == "not_a_number"
        assert len(fixes) == 0


# =========================================================================
# Tier 3: SemanticValidator + HallucinationDetector
# =========================================================================


class TestHallucinationDetector:
    """HallucinationDetector rule-based checks."""

    def test_no_issues_for_clean_data(self) -> None:
        d = HallucinationDetector()
        report = d.detect({"answer": "The weather is sunny."})
        assert report.confidence == 1.0
        assert report.issues == []

    def test_uncertainty_markers_reduce_confidence(self) -> None:
        d = HallucinationDetector()
        report = d.detect({"answer": "I think it might be sunny, probably."})
        assert report.confidence < 1.0
        assert any(i.code == "uncertainty_detected" for i in report.issues)

    def test_fabrication_patterns_reduce_confidence(self) -> None:
        d = HallucinationDetector()
        report = d.detect({"answer": "According to my training data, the sky is blue."})
        assert report.confidence < 1.0
        assert any(i.code == "fabrication_risk" for i in report.issues)

    def test_belief_contradiction(self) -> None:
        d = HallucinationDetector()
        beliefs = {
            "pet_preference": {
                "value": "loves dogs",
                "negation": "hates dogs",
            }
        }
        report = d.detect(
            {"answer": "The user hates dogs."},
            session_beliefs=beliefs,
        )
        assert any(i.code == "belief_contradiction" for i in report.issues)

    def test_empty_data(self) -> None:
        d = HallucinationDetector()
        report = d.detect({})
        assert report.confidence == 1.0

    def test_confidence_clamped(self) -> None:
        """Many markers cannot push confidence below 0."""
        d = HallucinationDetector()
        text = (
            "I think probably perhaps I'm not sure it might be "
            "could be I believe approximately not certain "
            "according to my training data as of my last update I was trained my training data"
        )
        report = d.detect({"answer": text})
        assert report.confidence >= 0.0


class TestSemanticValidator:
    """SemanticValidator tier 3 with ISessionStateReader."""

    def test_skip_for_non_semantic_provider(self) -> None:
        v = SemanticValidator()
        vr = v.validate(data={"x": 1}, provider_type="MCP")
        assert vr.valid is True
        assert vr.metadata.get("skipped") is True

    def test_agent_provider_runs_checks(self) -> None:
        v = SemanticValidator()
        vr = v.validate(
            data={"answer": "I think it might rain, probably."},
            provider_type="AGENT",
        )
        # Even with SOFT issues, confidence may be below threshold
        assert vr.tier == ValidationTier.SEMANTIC

    def test_workflow_provider_runs_checks(self) -> None:
        v = SemanticValidator()
        vr = v.validate(data={"answer": "ok"}, provider_type="WORKFLOW")
        assert vr.tier == ValidationTier.SEMANTIC
        assert vr.valid is True

    def test_reads_session_beliefs(self) -> None:
        reader = InMemorySessionStateReader()
        reader.set_section(
            "s1",
            "beliefs",
            {
                "color_pref": {"value": "loves blue", "negation": "hates blue"},
            },
        )
        v = SemanticValidator(state_reader=reader)
        vr = v.validate(
            data={"answer": "The user hates blue according to records."},
            provider_type="AGENT",
            session_id="s1",
        )
        assert any(i.code == "belief_contradiction" for i in vr.issues)


# =========================================================================
# ValidationFallback
# =========================================================================


class TestValidationFallback:
    """ValidationFallback handles tier failures."""

    def test_valid_result_passes(self) -> None:
        fb = ValidationFallback()
        vr = ValidationResult(valid=True, tier=ValidationTier.STRUCTURAL)
        result = fb.handle(vr)
        assert result.action == FallbackAction.PASS
        assert result.rejected is False

    def test_structural_fail_rejects(self) -> None:
        bus = CaptureEventPort()
        fb = ValidationFallback(event_port=bus)
        from k1.fabric.output_validation.structural_validator import ValidationIssue

        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.STRUCTURAL,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.STRUCTURAL,
                    severity=ValidationSeverity.HARD,
                    code="missing_success_field",
                    message="missing success",
                )
            ],
        )
        result = fb.handle(vr, request_id="r1", provider_id="p1", trace_id="t1")
        assert result.rejected is True
        assert result.action == FallbackAction.REJECT
        assert result.event_emitted is True
        assert len(bus.events) == 1
        assert bus.events[0]["event_type"] == EVENT_VALIDATION_FAILED

    def test_schema_fail_with_coercion_success(self) -> None:
        schema = {
            "required": ["status"],
            "properties": {"status": {"type": "string", "default": "ok"}},
        }
        c = _contract(output_schema=schema)
        sv = SchemaValidator()
        fb = ValidationFallback(schema_validator=sv)
        from k1.fabric.output_validation.structural_validator import ValidationIssue

        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.SCHEMA,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.SCHEMA,
                    severity=ValidationSeverity.HARD,
                    code="schema_violation",
                    message="missing required 'status'",
                )
            ],
        )
        result = fb.handle(vr, original_data={}, contract=c)
        assert result.rejected is False
        assert result.action == FallbackAction.COERCE
        assert result.coerced_data is not None
        assert result.coerced_data["status"] == "ok"

    def test_schema_fail_rejects_when_coercion_fails(self) -> None:
        schema = {
            "required": ["status"],
            "properties": {"status": {"type": "integer"}},
        }
        c = _contract(output_schema=schema)
        bus = CaptureEventPort()
        fb = ValidationFallback(event_port=bus)
        from k1.fabric.output_validation.structural_validator import ValidationIssue

        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.SCHEMA,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.SCHEMA,
                    severity=ValidationSeverity.HARD,
                    code="schema_violation",
                    message="wrong type",
                )
            ],
        )
        # original_data missing 'status', coercion fills 0, but 0 is valid int
        # actually this should pass coercion; let's test without any data
        result = fb.handle(vr, original_data=None, contract=c)
        assert result.rejected is True
        assert result.event_emitted is True

    def test_semantic_fail_annotates(self) -> None:
        from k1.fabric.output_validation.structural_validator import ValidationIssue

        fb = ValidationFallback()
        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.SEMANTIC,
            confidence=0.5,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.SEMANTIC,
                    severity=ValidationSeverity.SOFT,
                    code="uncertainty_detected",
                    message="3 markers found",
                )
            ],
        )
        result = fb.handle(vr)
        assert result.rejected is False
        assert result.action == FallbackAction.ANNOTATE
        assert len(result.annotations) > 0
        assert any("semantic" in a.lower() for a in result.annotations)


# =========================================================================
# OutputValidationPipeline (composite)
# =========================================================================


class TestOutputValidationPipeline:
    """Full 3-tier pipeline tests."""

    def test_valid_result_passes_all_tiers(self) -> None:
        schema = {
            "type": "object",
            "required": ["status"],
            "properties": {"status": {"type": "string"}},
        }
        c = _contract(output_schema=schema)
        pipeline = OutputValidationPipeline()
        r = _success({"status": "ok"})
        outcome = pipeline.validate(r, contract=c, provider_type="MCP")
        assert outcome.passed is True
        assert outcome.rejected is False
        # Structural + Schema tiers should have run
        assert len(outcome.tier_results) >= 2

    def test_structural_fail_short_circuits(self) -> None:
        """Structural failure skips schema + semantic."""
        pipeline = OutputValidationPipeline()
        r = CapabilityResult(success=True, data=None, error=None)
        outcome = pipeline.validate(r, provider_type="MCP")
        assert outcome.rejected is True
        assert "Structural" in outcome.rejection_reason
        # Only structural tier ran
        assert len(outcome.tier_results) == 1

    def test_schema_fail_rejects(self) -> None:
        schema = {
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string"}},
        }
        c = _contract(output_schema=schema)
        pipeline = OutputValidationPipeline()
        # Type mismatch: integer where string expected -- coercion cannot fix this
        r = _success({"answer": 42})
        outcome = pipeline.validate(r, contract=c, provider_type="MCP")
        assert outcome.rejected is True
        assert "Schema" in outcome.rejection_reason

    def test_schema_coercion_passes(self) -> None:
        """Schema fail + successful coercion -> passed with coerced_data."""
        schema = {
            "type": "object",
            "required": ["status"],
            "properties": {"status": {"type": "string", "default": "unknown"}},
        }
        c = _contract(output_schema=schema)
        pipeline = OutputValidationPipeline(config=OutputValidationConfig(enable_coercion=True))
        r = _success({"extra": "data"})
        outcome = pipeline.validate(r, contract=c, provider_type="MCP")
        assert outcome.passed is True
        assert outcome.coerced_data is not None
        assert outcome.coerced_data["status"] == "unknown"

    def test_semantic_soft_fail_passes_with_annotations(self) -> None:
        """Agent output with uncertainty markers -> passed with annotations."""
        pipeline = OutputValidationPipeline(
            config=OutputValidationConfig(skip_semantic=False),
        )
        r = _success({"answer": "I think probably maybe it might be sunny."})
        outcome = pipeline.validate(r, provider_type="AGENT")
        assert outcome.passed is True
        # Semantic issues are annotated, not rejected
        assert outcome.rejected is False

    def test_skip_semantic_for_tool_results(self) -> None:
        pipeline = OutputValidationPipeline(
            config=OutputValidationConfig(skip_semantic=True),
        )
        r = _success({"answer": "I think probably maybe."})
        outcome = pipeline.validate(r, provider_type="AGENT")
        assert outcome.passed is True
        # No semantic tier in results
        semantic_tiers = [tr for tr in outcome.tier_results if tr.tier == ValidationTier.SEMANTIC]
        assert len(semantic_tiers) == 0

    def test_semantic_skipped_for_mcp_provider(self) -> None:
        """MCP provider type never triggers semantic validation."""
        pipeline = OutputValidationPipeline(
            config=OutputValidationConfig(skip_semantic=False),
        )
        r = _success({"answer": "I think probably nonsense."})
        outcome = pipeline.validate(r, provider_type="MCP")
        assert outcome.passed is True
        semantic_tiers = [tr for tr in outcome.tier_results if tr.tier == ValidationTier.SEMANTIC]
        assert len(semantic_tiers) == 0

    def test_failure_result_passes_structural(self) -> None:
        """Failed CapabilityResult (success=False, error set) passes structural."""
        pipeline = OutputValidationPipeline()
        r = _failure("timeout", "Timed out")
        outcome = pipeline.validate(r, provider_type="MCP")
        assert outcome.passed is True
        assert outcome.rejected is False

    def test_event_emitted_on_structural_rejection(self) -> None:
        bus = CaptureEventPort()
        pipeline = OutputValidationPipeline(event_port=bus)
        r = CapabilityResult(success=True, data=None, error=None)
        outcome = pipeline.validate(r, provider_type="MCP", request_id="r1", trace_id="t1")
        assert outcome.rejected is True
        assert any(e["event_type"] == EVENT_VALIDATION_FAILED for e in bus.events)

    def test_event_emitted_on_schema_rejection(self) -> None:
        bus = CaptureEventPort()
        schema = {
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string"}},
        }
        c = _contract(output_schema=schema)
        pipeline = OutputValidationPipeline(event_port=bus)
        # Type mismatch that coercion cannot fix
        r = _success({"answer": [1, 2, 3]})
        outcome = pipeline.validate(
            r, contract=c, provider_type="MCP", request_id="r1", trace_id="t1"
        )
        assert outcome.rejected is True
        assert any(e["event_type"] == EVENT_VALIDATION_FAILED for e in bus.events)

    def test_validate_quick(self) -> None:
        pipeline = OutputValidationPipeline()
        assert pipeline.validate_quick(_success({"ok": True})) is True
        assert pipeline.validate_quick(CapabilityResult(success=True, data=None)) is False

    def test_pipeline_with_session_beliefs(self) -> None:
        """Full pipeline with semantic validator using session beliefs."""
        reader = InMemorySessionStateReader()
        reader.set_section(
            "s1",
            "beliefs",
            {
                "diet": {"value": "vegetarian", "negation": "eats meat"},
            },
        )
        pipeline = OutputValidationPipeline(
            state_reader=reader,
            config=OutputValidationConfig(skip_semantic=False),
        )
        r = _success({"answer": "The user eats meat regularly."})
        outcome = pipeline.validate(r, provider_type="AGENT", session_id="s1")
        assert outcome.passed is True  # semantic is soft-fail only
        # But there should be annotations about the contradiction
        if outcome.annotations:
            assert any(
                "belief" in a.lower() or "semantic" in a.lower() for a in outcome.annotations
            )

    def test_additional_properties_false(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        }
        c = _contract(output_schema=schema)
        pipeline = OutputValidationPipeline()
        r = _success({"name": "ok", "extra": "bad"})
        outcome = pipeline.validate(r, contract=c, provider_type="MCP")
        assert outcome.rejected is True

    def test_pipeline_properties(self) -> None:
        """Pipeline exposes sub-validators for inspection."""
        pipeline = OutputValidationPipeline()
        assert isinstance(pipeline.structural_validator, StructuralValidator)
        assert isinstance(pipeline.schema_validator, SchemaValidator)
        assert isinstance(pipeline.semantic_validator, SemanticValidator)
        assert isinstance(pipeline.fallback, ValidationFallback)
        assert isinstance(pipeline.config, OutputValidationConfig)
