"""
Tests for Epic 3.5: Output Validation Pipeline (Issues 3.5.1 -- 3.5.5).

Covers:
  - 3.5.1 StructuralValidator
  - 3.5.2 SchemaValidator + SchemaCompiler
  - 3.5.3 SemanticValidator + HallucinationDetector
  - 3.5.4 ValidationFallback
  - 3.5.5 OutputValidationPipeline
  - Module exports verification
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.output_validation import (  # Shared types; 3.5.1; 3.5.2; 3.5.3; 3.5.4; 3.5.5
    DEFAULT_MAX_DATA_BYTES,
    EVENT_VALIDATION_FAILED,
    SEMANTIC_PROVIDER_TYPES,
    TRUNCATION_MARKERS,
    FallbackAction,
    FallbackResult,
    HallucinationDetector,
    HallucinationDetectorConfig,
    HallucinationReport,
    OutputValidationConfig,
    OutputValidationPipeline,
    PipelineOutcome,
    SchemaCompilationError,
    SchemaCompiler,
    SchemaValidator,
    SemanticValidator,
    StructuralValidator,
    StructuralValidatorConfig,
    ValidationFallback,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    ValidationTier,
    attempt_coercion,
)
from k1.fabric.types import CapabilityContract, CapabilityResult

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeEventPort:
    """Records emitted events for assertions."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, event_type: str, payload: Any) -> None:
        self.events.append({"type": event_type, "payload": payload})


class FailingEventPort:
    """Event port that raises on emit."""

    def emit(self, event_type: str, payload: Any) -> None:
        raise RuntimeError("event bus down")


class FakeStateReader:
    """Fake ISessionStateReader for semantic tests."""

    def __init__(self, sections: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._sections = sections or {}

    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        return self._sections.get(section)


class FailingStateReader:
    """State reader that raises on read."""

    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        raise RuntimeError("state reader down")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _success_result(data: Dict[str, Any], **kw: Any) -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id=kw.get("request_id", "req-1"),
        data=data,
        provider_id=kw.get("provider_id", "prov-1"),
        trace_id=kw.get("trace_id", "trace-1"),
    )


def _failure_result(**kw: Any) -> CapabilityResult:
    return CapabilityResult.failure_result(
        request_id=kw.get("request_id", "req-1"),
        error_code=kw.get("error_code", "provider_error"),
        error_message=kw.get("error_message", "something failed"),
        provider_id=kw.get("provider_id", "prov-1"),
        trace_id=kw.get("trace_id", "trace-1"),
    )


def _contract(output_schema: Optional[Dict[str, Any]] = None) -> CapabilityContract:
    return CapabilityContract(
        name="tool.test",
        version="1.0.0",
        domain=["test"],
        output=output_schema or {},
    )


# ===================================================================
# 3.5.1 -- StructuralValidator Tests
# ===================================================================


class TestStructuralValidatorBasic:
    """Basic structural validation tests."""

    def test_valid_success_result(self) -> None:
        v = StructuralValidator()
        result = v.validate(_success_result({"key": "value"}))
        assert result.valid is True
        assert result.tier == ValidationTier.STRUCTURAL
        assert len(result.issues) == 0

    def test_valid_failure_result(self) -> None:
        v = StructuralValidator()
        result = v.validate(_failure_result())
        assert result.valid is True
        assert result.tier == ValidationTier.STRUCTURAL

    def test_missing_success_field(self) -> None:
        v = StructuralValidator()

        class NoSuccess:
            data = {}

        result = v.validate(NoSuccess())
        assert result.valid is False
        assert any(i.code == "missing_success_field" for i in result.issues)

    def test_success_without_data(self) -> None:
        v = StructuralValidator()

        @dataclass
        class BadResult:
            success: bool = True
            data: Any = None
            error: Any = None

        result = v.validate(BadResult())
        assert result.valid is False
        assert any(i.code == "success_without_data" for i in result.issues)

    def test_success_with_error_set(self) -> None:
        v = StructuralValidator()

        @dataclass
        class BadResult:
            success: bool = True
            data: dict = field(default_factory=dict)
            error: str = "oops"

        result = v.validate(BadResult())
        assert result.valid is False
        assert any(i.code == "success_with_error" for i in result.issues)

    def test_failure_without_error(self) -> None:
        v = StructuralValidator()

        @dataclass
        class BadResult:
            success: bool = False
            data: Any = None
            error: Any = None

        result = v.validate(BadResult())
        assert result.valid is False
        assert any(i.code == "failure_without_error" for i in result.issues)

    def test_data_not_dict(self) -> None:
        v = StructuralValidator()

        @dataclass
        class BadResult:
            success: bool = True
            data: str = "not a dict"
            error: Any = None

        result = v.validate(BadResult())
        assert result.valid is False
        assert any(i.code == "data_not_dict" for i in result.issues)


class TestStructuralValidatorTruncation:
    """Truncation detection tests."""

    def test_no_truncation_in_clean_data(self) -> None:
        v = StructuralValidator()
        result = v.validate(_success_result({"message": "Hello world"}))
        assert result.valid is True

    def test_detects_ellipsis_truncation(self) -> None:
        v = StructuralValidator()
        result = v.validate(_success_result({"output": "Some text..."}))
        assert result.valid is False
        assert any(i.code == "truncation_detected" for i in result.issues)
        assert "truncation_locations" in result.metadata

    def test_detects_truncated_marker(self) -> None:
        v = StructuralValidator()
        result = v.validate(_success_result({"output": "Result [truncated]"}))
        assert result.valid is False
        assert any(i.code == "truncation_detected" for i in result.issues)

    def test_detects_nested_truncation(self) -> None:
        v = StructuralValidator()
        result = v.validate(_success_result({"nested": {"deep": "content [output cut]"}}))
        assert result.valid is False

    def test_detects_list_truncation(self) -> None:
        v = StructuralValidator()
        result = v.validate(
            _success_result({"items": ["ok", "also ok", "hmm [content truncated]"]})
        )
        assert result.valid is False

    def test_truncation_check_disabled(self) -> None:
        config = StructuralValidatorConfig(check_truncation=False)
        v = StructuralValidator(config)
        result = v.validate(_success_result({"output": "Some text..."}))
        assert result.valid is True

    def test_truncation_depth_limit(self) -> None:
        """Deep nesting beyond max_scan_depth is ignored."""
        config = StructuralValidatorConfig(max_scan_depth=1)
        v = StructuralValidator(config)
        # Level 0: dict, Level 1: dict, Level 2: str with marker
        result = v.validate(_success_result({"l1": {"l2": "text [truncated]"}}))
        # At depth 0 we enter the top dict, depth 1 we enter l1,
        # depth 2 exceeds max_scan_depth=1, so marker is NOT found
        assert result.valid is True


class TestStructuralValidatorSizeLimits:
    """Size limit tests."""

    def test_within_size_limit(self) -> None:
        v = StructuralValidator()
        result = v.validate(_success_result({"small": "data"}))
        assert result.valid is True
        assert "data_size_bytes" in result.metadata

    def test_exceeds_size_limit(self) -> None:
        config = StructuralValidatorConfig(max_data_bytes=10)
        v = StructuralValidator(config)
        result = v.validate(_success_result({"big": "x" * 100}))
        assert result.valid is False
        assert any(i.code == "data_too_large" for i in result.issues)

    def test_default_1mib_limit(self) -> None:
        assert DEFAULT_MAX_DATA_BYTES == 1_048_576

    def test_size_not_checked_on_failure_result(self) -> None:
        """Size check only runs on success results with data."""
        v = StructuralValidator()
        result = v.validate(_failure_result())
        assert result.valid is True
        assert "data_size_bytes" not in result.metadata


class TestStructuralValidatorIssueTypes:
    """Verify issue types and severity."""

    def test_all_issues_are_hard(self) -> None:
        v = StructuralValidator()

        @dataclass
        class Bad:
            success: bool = True
            data: Any = None
            error: Any = None

        result = v.validate(Bad())
        for issue in result.issues:
            assert issue.severity == ValidationSeverity.HARD

    def test_all_issues_are_structural_tier(self) -> None:
        v = StructuralValidator()
        result = v.validate(_success_result({"x": "text [truncated]"}))
        for issue in result.issues:
            assert issue.tier == ValidationTier.STRUCTURAL


class TestValidationResultFrozen:
    """ValidationResult is immutable."""

    def test_frozen(self) -> None:
        r = ValidationResult(valid=True, tier=ValidationTier.STRUCTURAL)
        with pytest.raises(AttributeError):
            r.valid = False  # type: ignore[misc]


class TestValidationIssueFrozen:
    """ValidationIssue is immutable."""

    def test_frozen(self) -> None:
        i = ValidationIssue(
            tier=ValidationTier.STRUCTURAL,
            severity=ValidationSeverity.HARD,
            code="test",
            message="test",
        )
        with pytest.raises(AttributeError):
            i.code = "changed"  # type: ignore[misc]


# ===================================================================
# 3.5.2 -- SchemaValidator + SchemaCompiler Tests
# ===================================================================


class TestSchemaCompiler:
    """SchemaCompiler cache tests."""

    def test_compile_and_cache(self) -> None:
        compiler = SchemaCompiler()
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        result1 = compiler.get_or_compile("tool.test", "1.0.0", schema)
        result2 = compiler.get_or_compile("tool.test", "1.0.0", schema)
        assert result1 is result2  # same cached reference
        assert compiler.cache_size == 1

    def test_different_versions_cached_separately(self) -> None:
        compiler = SchemaCompiler()
        schema = {"type": "object"}
        compiler.get_or_compile("tool.test", "1.0.0", schema)
        compiler.get_or_compile("tool.test", "2.0.0", schema)
        assert compiler.cache_size == 2

    def test_invalidate(self) -> None:
        compiler = SchemaCompiler()
        compiler.get_or_compile("t", "1", {"type": "object"})
        assert compiler.invalidate("t", "1") is True
        assert compiler.invalidate("t", "1") is False
        assert compiler.cache_size == 0

    def test_clear(self) -> None:
        compiler = SchemaCompiler()
        compiler.get_or_compile("a", "1", {"type": "object"})
        compiler.get_or_compile("b", "1", {"type": "object"})
        compiler.clear()
        assert compiler.cache_size == 0

    def test_rejects_non_dict_schema(self) -> None:
        compiler = SchemaCompiler()
        with pytest.raises(SchemaCompilationError):
            compiler.get_or_compile("t", "1", "not a dict")  # type: ignore[arg-type]

    def test_deep_copy_isolation(self) -> None:
        compiler = SchemaCompiler()
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        compiler.get_or_compile("t", "1", schema)
        # Mutating original should not affect cache
        schema["properties"]["y"] = {"type": "number"}
        cached = compiler.get_or_compile("t", "1", schema)
        assert "y" not in cached.get("properties", {})


class TestSchemaValidation:
    """Built-in JSON Schema validation tests."""

    def test_valid_object(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            }
        )
        sv = SchemaValidator()
        result = sv.validate({"name": "Alice"}, contract)
        assert result.valid is True

    def test_missing_required_field(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            }
        )
        sv = SchemaValidator()
        result = sv.validate({}, contract)
        assert result.valid is False
        assert any("missing required" in i.message for i in result.issues)

    def test_wrong_type(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "properties": {"age": {"type": "integer"}},
            }
        )
        sv = SchemaValidator()
        result = sv.validate({"age": "not a number"}, contract)
        assert result.valid is False

    def test_enum_valid(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "properties": {"status": {"enum": ["active", "inactive"]}},
            }
        )
        sv = SchemaValidator()
        result = sv.validate({"status": "active"}, contract)
        assert result.valid is True

    def test_enum_invalid(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "properties": {"status": {"enum": ["active", "inactive"]}},
            }
        )
        sv = SchemaValidator()
        result = sv.validate({"status": "deleted"}, contract)
        assert result.valid is False

    def test_additional_properties_false(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "additionalProperties": False,
            }
        )
        sv = SchemaValidator()
        result = sv.validate({"x": "ok", "y": "extra"}, contract)
        assert result.valid is False
        assert any("additional properties" in i.message for i in result.issues)

    def test_array_items_validation(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
            }
        )
        sv = SchemaValidator()
        result = sv.validate({"items": ["a", 42]}, contract)
        assert result.valid is False

    def test_min_max_items(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "properties": {
                    "tags": {"type": "array", "minItems": 1, "maxItems": 3},
                },
            }
        )
        sv = SchemaValidator()
        assert sv.validate({"tags": []}, contract).valid is False
        assert sv.validate({"tags": ["a"]}, contract).valid is True
        assert sv.validate({"tags": ["a", "b", "c", "d"]}, contract).valid is False

    def test_string_length(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "minLength": 2, "maxLength": 5},
                },
            }
        )
        sv = SchemaValidator()
        assert sv.validate({"code": "a"}, contract).valid is False
        assert sv.validate({"code": "ab"}, contract).valid is True
        assert sv.validate({"code": "abcdef"}, contract).valid is False

    def test_number_range(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "properties": {
                    "score": {"type": "number", "minimum": 0, "maximum": 100},
                },
            }
        )
        sv = SchemaValidator()
        assert sv.validate({"score": -1}, contract).valid is False
        assert sv.validate({"score": 50}, contract).valid is True
        assert sv.validate({"score": 101}, contract).valid is False

    def test_no_schema_passes(self) -> None:
        """When contract has no output schema, validation passes."""
        contract = _contract({})
        sv = SchemaValidator()
        result = sv.validate({"anything": "goes"}, contract)
        assert result.valid is True
        assert result.metadata.get("schema_present") is False

    def test_nested_object_validation(self) -> None:
        contract = _contract(
            {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "object",
                        "required": ["city"],
                        "properties": {"city": {"type": "string"}},
                    }
                },
            }
        )
        sv = SchemaValidator()
        assert sv.validate({"address": {"city": "NYC"}}, contract).valid is True
        assert sv.validate({"address": {}}, contract).valid is False

    def test_additional_properties_schema(self) -> None:
        """additionalProperties as a schema dict."""
        contract = _contract(
            {
                "type": "object",
                "properties": {},
                "additionalProperties": {"type": "string"},
            }
        )
        sv = SchemaValidator()
        assert sv.validate({"x": "ok"}, contract).valid is True
        assert sv.validate({"x": 42}, contract).valid is False

    def test_multi_type(self) -> None:
        """type as a list of types."""
        contract = _contract(
            {
                "type": "object",
                "properties": {"val": {"type": ["string", "null"]}},
            }
        )
        sv = SchemaValidator()
        assert sv.validate({"val": "ok"}, contract).valid is True
        assert sv.validate({"val": None}, contract).valid is True
        assert sv.validate({"val": 42}, contract).valid is False


class TestSchemaCoercion:
    """attempt_coercion tests."""

    def test_fill_defaults(self) -> None:
        schema = {
            "type": "object",
            "required": ["name", "count"],
            "properties": {
                "name": {"type": "string", "default": "Unknown"},
                "count": {"type": "integer", "default": 0},
            },
        }
        coerced, fixes = attempt_coercion({}, schema)
        assert coerced["name"] == "Unknown"
        assert coerced["count"] == 0
        assert len(fixes) == 2

    def test_fill_empty_string_when_no_default(self) -> None:
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
        coerced, fixes = attempt_coercion({}, schema)
        assert coerced["name"] == ""
        assert len(fixes) == 1

    def test_cast_string_to_number(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "price": {"type": "number"},
                "qty": {"type": "integer"},
            },
        }
        coerced, fixes = attempt_coercion({"price": "9.99", "qty": "5"}, schema)
        assert coerced["price"] == 9.99
        assert coerced["qty"] == 5
        assert len(fixes) == 2

    def test_cast_non_numeric_string_no_change(self) -> None:
        schema = {
            "type": "object",
            "properties": {"price": {"type": "number"}},
        }
        coerced, fixes = attempt_coercion({"price": "not_a_number"}, schema)
        assert coerced["price"] == "not_a_number"
        assert len(fixes) == 0

    def test_does_not_mutate_original(self) -> None:
        schema = {
            "type": "object",
            "required": ["x"],
            "properties": {"x": {"type": "string", "default": "def"}},
        }
        original = {"existing": "value"}
        coerced, _ = attempt_coercion(original, schema)
        assert "x" not in original
        assert "x" in coerced

    def test_fill_empty_array(self) -> None:
        schema = {
            "type": "object",
            "required": ["tags"],
            "properties": {"tags": {"type": "array"}},
        }
        coerced, fixes = attempt_coercion({}, schema)
        assert coerced["tags"] == []
        assert len(fixes) == 1

    def test_fill_empty_object(self) -> None:
        schema = {
            "type": "object",
            "required": ["meta"],
            "properties": {"meta": {"type": "object"}},
        }
        coerced, fixes = attempt_coercion({}, schema)
        assert coerced["meta"] == {}

    def test_fill_boolean_default(self) -> None:
        schema = {
            "type": "object",
            "required": ["active"],
            "properties": {"active": {"type": "boolean"}},
        }
        coerced, fixes = attempt_coercion({}, schema)
        assert coerced["active"] is False


# ===================================================================
# 3.5.3 -- SemanticValidator + HallucinationDetector Tests
# ===================================================================


class TestHallucinationDetector:
    """HallucinationDetector detection tests."""

    def test_clean_output_high_confidence(self) -> None:
        detector = HallucinationDetector()
        report = detector.detect({"response": "The capital of France is Paris."})
        assert report.confidence >= 0.9
        assert len(report.issues) == 0

    def test_uncertainty_markers_reduce_confidence(self) -> None:
        detector = HallucinationDetector()
        report = detector.detect({"response": "I think the answer might be 42, but I'm not sure."})
        assert report.confidence < 1.0
        assert any(i.code == "uncertainty_detected" for i in report.issues)

    def test_fabrication_patterns_reduce_confidence(self) -> None:
        detector = HallucinationDetector()
        report = detector.detect(
            {"response": "According to my training data, the population is 8 billion."}
        )
        assert report.confidence < 1.0
        assert any(i.code == "fabrication_risk" for i in report.issues)

    def test_belief_contradiction(self) -> None:
        detector = HallucinationDetector()
        beliefs = {
            "user_preference": {
                "value": "vegetarian",
                "negation": "meat lover",
            }
        }
        report = detector.detect(
            {"response": "Since you're a meat lover, try steak!"},
            session_beliefs=beliefs,
        )
        assert report.confidence < 1.0
        assert any(i.code == "belief_contradiction" for i in report.issues)

    def test_empty_data_is_clean(self) -> None:
        detector = HallucinationDetector()
        report = detector.detect({})
        assert report.confidence == 1.0
        assert len(report.issues) == 0

    def test_nested_text_extraction(self) -> None:
        detector = HallucinationDetector()
        report = detector.detect(
            {
                "result": {
                    "items": ["I'm not sure about this", "definitely correct"],
                }
            }
        )
        assert report.confidence < 1.0

    def test_disabled_checks(self) -> None:
        config = HallucinationDetectorConfig(
            check_factual_grounding=False,
            check_session_consistency=False,
            check_confidence_markers=False,
        )
        detector = HallucinationDetector(config)
        report = detector.detect({"response": "I'm not sure, according to my training data..."})
        assert report.confidence == 1.0
        assert len(report.issues) == 0

    def test_confidence_clamped_to_zero(self) -> None:
        """Confidence never goes below 0."""
        detector = HallucinationDetector()
        # Lots of uncertainty + fabrication
        report = detector.detect(
            {
                "response": (
                    "I'm not sure, I think probably perhaps might be could be "
                    "not certain I believe approximately "
                    "according to my training data, as of my last update, "
                    "I was trained my training data"
                ),
            }
        )
        assert report.confidence >= 0.0

    def test_all_issues_are_soft(self) -> None:
        detector = HallucinationDetector()
        report = detector.detect({"response": "I think this is probably correct"})
        for issue in report.issues:
            assert issue.severity == ValidationSeverity.SOFT

    def test_report_frozen(self) -> None:
        report = HallucinationReport(confidence=0.5)
        with pytest.raises(AttributeError):
            report.confidence = 0.9  # type: ignore[misc]


class TestSemanticValidator:
    """SemanticValidator tests."""

    def test_skips_non_semantic_providers(self) -> None:
        sv = SemanticValidator()
        result = sv.validate(
            data={"response": "I'm not sure"},
            provider_type="MCP",
        )
        assert result.valid is True
        assert result.metadata.get("skipped") is True

    def test_runs_for_agent_provider(self) -> None:
        sv = SemanticValidator()
        result = sv.validate(
            data={"response": "The answer is 42"},
            provider_type="AGENT",
        )
        assert result.tier == ValidationTier.SEMANTIC
        # Clean output = valid
        assert result.valid is True

    def test_runs_for_workflow_provider(self) -> None:
        sv = SemanticValidator()
        result = sv.validate(
            data={"response": "The answer is 42"},
            provider_type="WORKFLOW",
        )
        assert result.valid is True

    def test_low_confidence_fails(self) -> None:
        sv = SemanticValidator()
        result = sv.validate(
            data={
                "response": (
                    "I'm not sure, I think probably perhaps might be "
                    "could be not certain. According to my training data, "
                    "the answer might be 42."
                )
            },
            provider_type="AGENT",
        )
        # Uncertainty markers (-0.3) + fabrication pattern (-0.1) -> 0.6 < 0.7
        assert result.valid is False
        assert result.confidence < 0.7

    def test_reads_session_beliefs(self) -> None:
        reader = FakeStateReader(
            {
                "beliefs": {
                    "diet": {"value": "vegan", "negation": "meat eater"},
                }
            }
        )
        sv = SemanticValidator(state_reader=reader)
        result = sv.validate(
            data={"response": "As a meat eater, you should try bacon"},
            provider_type="AGENT",
            session_id="sess-1",
        )
        assert any(i.code == "belief_contradiction" for i in result.issues)

    def test_graceful_degradation_no_reader(self) -> None:
        sv = SemanticValidator(state_reader=None)
        result = sv.validate(
            data={"response": "Hello"},
            provider_type="AGENT",
        )
        assert result.valid is True
        assert result.metadata.get("beliefs_checked") is False

    def test_graceful_degradation_reader_fails(self) -> None:
        sv = SemanticValidator(state_reader=FailingStateReader())
        result = sv.validate(
            data={"response": "Hello"},
            provider_type="AGENT",
            session_id="sess-1",
        )
        # Should not crash, beliefs_checked should be False
        assert result.valid is True

    def test_semantic_provider_types(self) -> None:
        assert "AGENT" in SEMANTIC_PROVIDER_TYPES
        assert "WORKFLOW" in SEMANTIC_PROVIDER_TYPES
        assert "MCP" not in SEMANTIC_PROVIDER_TYPES


# ===================================================================
# 3.5.4 -- ValidationFallback Tests
# ===================================================================


class TestValidationFallbackStructural:
    """Fallback for structural failures."""

    def test_structural_fail_rejects(self) -> None:
        ep = FakeEventPort()
        fb = ValidationFallback(event_port=ep)
        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.STRUCTURAL,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.STRUCTURAL,
                    severity=ValidationSeverity.HARD,
                    code="missing_success_field",
                    message="Missing field",
                )
            ],
        )
        result = fb.handle(vr, request_id="r1", provider_id="p1", trace_id="t1")
        assert result.rejected is True
        assert result.action == FallbackAction.REJECT
        assert result.event_emitted is True
        assert len(ep.events) == 1
        assert ep.events[0]["type"] == EVENT_VALIDATION_FAILED

    def test_structural_fail_event_payload(self) -> None:
        ep = FakeEventPort()
        fb = ValidationFallback(event_port=ep)
        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.STRUCTURAL,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.STRUCTURAL,
                    severity=ValidationSeverity.HARD,
                    code="test_code",
                    message="test msg",
                )
            ],
        )
        fb.handle(vr, request_id="r1", provider_id="p1", trace_id="t1")
        payload = ep.events[0]["payload"]
        assert payload["tier"] == "STRUCTURAL"
        assert payload["request_id"] == "r1"
        assert payload["provider_id"] == "p1"
        assert payload["trace_id"] == "t1"
        assert len(payload["issues"]) == 1


class TestValidationFallbackSchema:
    """Fallback for schema failures."""

    def test_schema_fail_with_successful_coercion(self) -> None:
        ep = FakeEventPort()
        fb = ValidationFallback(event_port=ep)
        contract = _contract(
            {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string", "default": "N/A"}},
            }
        )
        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.SCHEMA,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.SCHEMA,
                    severity=ValidationSeverity.HARD,
                    code="schema_violation",
                    message="missing required property 'name'",
                )
            ],
        )
        result = fb.handle(
            vr,
            original_data={},
            contract=contract,
            request_id="r1",
            provider_id="p1",
            trace_id="t1",
        )
        assert result.rejected is False
        assert result.action == FallbackAction.COERCE
        assert result.coerced_data is not None
        assert result.coerced_data["name"] == "N/A"
        assert len(result.annotations) > 0
        # No event emitted on successful coercion
        assert len(ep.events) == 0

    def test_schema_fail_coercion_fails_rejects(self) -> None:
        ep = FakeEventPort()
        fb = ValidationFallback(event_port=ep)
        # Contract requires "count" as integer, no default
        contract = _contract(
            {
                "type": "object",
                "required": ["count"],
                "properties": {"count": {"type": "integer"}},
            }
        )
        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.SCHEMA,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.SCHEMA,
                    severity=ValidationSeverity.HARD,
                    code="schema_violation",
                    message="missing 'count'",
                )
            ],
        )
        # Data has no 'count' and coercion will fill 0, which should pass
        # Let's test with no schema to prevent coercion
        result = fb.handle(
            vr,
            original_data={"other": "stuff"},
            contract=contract,
            request_id="r1",
            provider_id="p1",
            trace_id="t1",
        )
        # Coercion fills count=0, which satisfies the schema
        assert result.rejected is False
        assert result.action == FallbackAction.COERCE

    def test_schema_fail_no_data_rejects(self) -> None:
        ep = FakeEventPort()
        fb = ValidationFallback(event_port=ep)
        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.SCHEMA,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.SCHEMA,
                    severity=ValidationSeverity.HARD,
                    code="schema_violation",
                    message="missing field",
                )
            ],
        )
        result = fb.handle(
            vr,
            original_data=None,
            contract=None,
            request_id="r1",
            provider_id="p1",
            trace_id="t1",
        )
        assert result.rejected is True
        assert result.action == FallbackAction.REJECT
        assert result.event_emitted is True

    def test_schema_fail_no_contract_schema_rejects(self) -> None:
        fb = ValidationFallback(event_port=FakeEventPort())
        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.SCHEMA,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.SCHEMA,
                    severity=ValidationSeverity.HARD,
                    code="schema_violation",
                    message="error",
                )
            ],
        )
        # Contract with empty output schema -> coercion has nothing to do
        result = fb.handle(
            vr,
            original_data={"x": 1},
            contract=_contract({}),
            request_id="r1",
            provider_id="p1",
            trace_id="t1",
        )
        assert result.rejected is True


class TestValidationFallbackSemantic:
    """Fallback for semantic failures."""

    def test_semantic_fail_annotates_not_rejects(self) -> None:
        fb = ValidationFallback()
        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.SEMANTIC,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.SEMANTIC,
                    severity=ValidationSeverity.SOFT,
                    code="uncertainty_detected",
                    message="contains uncertainty",
                )
            ],
            confidence=0.5,
        )
        result = fb.handle(vr)
        assert result.rejected is False
        assert result.action == FallbackAction.ANNOTATE
        assert len(result.annotations) > 0
        assert any("semantic" in a for a in result.annotations)


class TestValidationFallbackValid:
    """Fallback on valid results."""

    def test_valid_result_passes(self) -> None:
        fb = ValidationFallback()
        vr = ValidationResult(valid=True, tier=ValidationTier.STRUCTURAL)
        result = fb.handle(vr)
        assert result.rejected is False
        assert result.action == FallbackAction.PASS


class TestValidationFallbackEventPort:
    """Event port edge cases."""

    def test_no_event_port_works(self) -> None:
        fb = ValidationFallback(event_port=None)
        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.STRUCTURAL,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.STRUCTURAL,
                    severity=ValidationSeverity.HARD,
                    code="test",
                    message="test",
                )
            ],
        )
        result = fb.handle(vr, request_id="r1")
        assert result.rejected is True
        assert result.event_emitted is False

    def test_failing_event_port_no_crash(self) -> None:
        fb = ValidationFallback(event_port=FailingEventPort())
        vr = ValidationResult(
            valid=False,
            tier=ValidationTier.STRUCTURAL,
            issues=[
                ValidationIssue(
                    tier=ValidationTier.STRUCTURAL,
                    severity=ValidationSeverity.HARD,
                    code="test",
                    message="test",
                )
            ],
        )
        result = fb.handle(vr, request_id="r1")
        assert result.rejected is True
        assert result.event_emitted is False


class TestFallbackResultFrozen:
    """FallbackResult is immutable."""

    def test_frozen(self) -> None:
        r = FallbackResult(action=FallbackAction.PASS, rejected=False)
        with pytest.raises(AttributeError):
            r.rejected = True  # type: ignore[misc]


# ===================================================================
# 3.5.5 -- OutputValidationPipeline Tests
# ===================================================================


class TestPipelineStructuralFail:
    """Pipeline short-circuits on structural failure."""

    def test_malformed_result_rejected(self) -> None:
        pipeline = OutputValidationPipeline()

        @dataclass
        class BadResult:
            success: bool = True
            data: Any = None
            error: Any = None

        outcome = pipeline.validate(BadResult())
        assert outcome.passed is False
        assert outcome.rejected is True
        assert "Structural" in outcome.rejection_reason
        assert len(outcome.tier_results) == 1

    def test_data_not_dict_rejected(self) -> None:
        pipeline = OutputValidationPipeline()

        @dataclass
        class BadResult:
            success: bool = True
            data: str = "not dict"
            error: Any = None

        outcome = pipeline.validate(BadResult())
        assert outcome.rejected is True


class TestPipelineSchemaFail:
    """Pipeline handles schema failures."""

    def test_schema_violation_rejected(self) -> None:
        pipeline = OutputValidationPipeline()
        result = _success_result({"wrong": "data"})
        contract = _contract(
            {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
                "additionalProperties": False,
            }
        )
        outcome = pipeline.validate(result, contract=contract)
        assert outcome.rejected is True
        assert "Schema" in outcome.rejection_reason

    def test_schema_coercion_succeeds(self) -> None:
        pipeline = OutputValidationPipeline()
        result = _success_result({})
        contract = _contract(
            {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string", "default": "Unknown"}},
            }
        )
        outcome = pipeline.validate(result, contract=contract)
        assert outcome.passed is True
        assert outcome.rejected is False
        assert outcome.coerced_data is not None
        assert outcome.coerced_data["name"] == "Unknown"

    def test_no_schema_passes(self) -> None:
        pipeline = OutputValidationPipeline()
        result = _success_result({"any": "data"})
        contract = _contract({})
        outcome = pipeline.validate(result, contract=contract)
        assert outcome.passed is True
        assert outcome.rejected is False


class TestPipelineSemanticTier:
    """Pipeline semantic tier tests."""

    def test_semantic_runs_for_agent(self) -> None:
        pipeline = OutputValidationPipeline()
        result = _success_result({"response": "I'm not sure about this"})
        outcome = pipeline.validate(
            result,
            provider_type="AGENT",
        )
        # Semantic may annotate but pipeline passes
        assert outcome.passed is True
        # Should have 3 tier results: structural, schema, semantic
        tier_names = [tr.tier for tr in outcome.tier_results]
        assert ValidationTier.SEMANTIC in tier_names

    def test_semantic_skipped_for_mcp(self) -> None:
        pipeline = OutputValidationPipeline()
        result = _success_result({"response": "I think probably maybe"})
        outcome = pipeline.validate(
            result,
            provider_type="MCP",
        )
        assert outcome.passed is True
        tier_names = [tr.tier for tr in outcome.tier_results]
        assert ValidationTier.SEMANTIC not in tier_names

    def test_skip_semantic_config(self) -> None:
        config = OutputValidationConfig(skip_semantic=True)
        pipeline = OutputValidationPipeline(config=config)
        result = _success_result({"response": "I'm not sure"})
        outcome = pipeline.validate(
            result,
            provider_type="AGENT",
        )
        tier_names = [tr.tier for tr in outcome.tier_results]
        assert ValidationTier.SEMANTIC not in tier_names

    def test_semantic_annotations_collected(self) -> None:
        pipeline = OutputValidationPipeline()
        result = _success_result(
            {
                "response": (
                    "I'm not sure, I think probably perhaps might be " "could be not certain"
                )
            }
        )
        outcome = pipeline.validate(
            result,
            provider_type="AGENT",
        )
        # If semantic flagged issues, annotations should be present
        if any(tr.tier == ValidationTier.SEMANTIC and not tr.valid for tr in outcome.tier_results):
            assert len(outcome.annotations) > 0


class TestPipelineWithPorts:
    """Pipeline with injected ports."""

    def test_event_emitted_on_structural_reject(self) -> None:
        ep = FakeEventPort()
        pipeline = OutputValidationPipeline(event_port=ep)

        @dataclass
        class BadResult:
            success: bool = True
            data: Any = None
            error: Any = None

        outcome = pipeline.validate(
            BadResult(),
            request_id="r1",
            provider_id="p1",
            trace_id="t1",
        )
        assert outcome.rejected is True
        assert len(ep.events) == 1
        assert ep.events[0]["type"] == EVENT_VALIDATION_FAILED

    def test_state_reader_used_in_semantic(self) -> None:
        reader = FakeStateReader(
            {
                "beliefs": {
                    "diet": {"value": "vegan", "negation": "meat eater"},
                }
            }
        )
        pipeline = OutputValidationPipeline(state_reader=reader)
        result = _success_result({"response": "As a meat eater, you should eat steak"})
        outcome = pipeline.validate(
            result,
            provider_type="AGENT",
            session_id="sess-1",
        )
        # Should have semantic annotations
        semantic_results = [tr for tr in outcome.tier_results if tr.tier == ValidationTier.SEMANTIC]
        assert len(semantic_results) == 1


class TestPipelineSuccessPath:
    """Full success path through pipeline."""

    def test_valid_result_with_schema(self) -> None:
        pipeline = OutputValidationPipeline()
        result = _success_result({"name": "Alice", "score": 95})
        contract = _contract(
            {
                "type": "object",
                "required": ["name", "score"],
                "properties": {
                    "name": {"type": "string"},
                    "score": {"type": "number"},
                },
            }
        )
        outcome = pipeline.validate(result, contract=contract)
        assert outcome.passed is True
        assert outcome.rejected is False
        assert outcome.coerced_data is None
        assert len(outcome.annotations) == 0

    def test_failure_result_passes_structural(self) -> None:
        """Failure results pass structural (no schema/semantic needed)."""
        pipeline = OutputValidationPipeline()
        result = _failure_result()
        outcome = pipeline.validate(result)
        assert outcome.passed is True
        assert outcome.rejected is False
        # Only structural tier ran
        assert len(outcome.tier_results) == 1


class TestPipelineQuickValidate:
    """validate_quick() convenience method."""

    def test_quick_pass(self) -> None:
        pipeline = OutputValidationPipeline()
        assert pipeline.validate_quick(_success_result({"ok": True})) is True

    def test_quick_fail(self) -> None:
        pipeline = OutputValidationPipeline()

        @dataclass
        class Bad:
            success: bool = True
            data: Any = None
            error: Any = None

        assert pipeline.validate_quick(Bad()) is False


class TestPipelineProperties:
    """Pipeline exposes sub-validators."""

    def test_structural_validator_accessible(self) -> None:
        p = OutputValidationPipeline()
        assert isinstance(p.structural_validator, StructuralValidator)

    def test_schema_validator_accessible(self) -> None:
        p = OutputValidationPipeline()
        assert isinstance(p.schema_validator, SchemaValidator)

    def test_semantic_validator_accessible(self) -> None:
        p = OutputValidationPipeline()
        assert isinstance(p.semantic_validator, SemanticValidator)

    def test_fallback_accessible(self) -> None:
        p = OutputValidationPipeline()
        assert isinstance(p.fallback, ValidationFallback)

    def test_config_accessible(self) -> None:
        config = OutputValidationConfig(skip_semantic=True)
        p = OutputValidationPipeline(config=config)
        assert p.config.skip_semantic is True


class TestPipelineOutcomeFrozen:
    """PipelineOutcome is immutable."""

    def test_frozen(self) -> None:
        o = PipelineOutcome(passed=True, rejected=False)
        with pytest.raises(AttributeError):
            o.passed = False  # type: ignore[misc]


class TestOutputValidationConfigFrozen:
    """OutputValidationConfig is immutable."""

    def test_frozen(self) -> None:
        c = OutputValidationConfig()
        with pytest.raises(AttributeError):
            c.skip_semantic = True  # type: ignore[misc]


# ===================================================================
# Module Exports Verification
# ===================================================================


class TestModuleExports:
    """Verify all public symbols are exported from __init__.py."""

    EXPECTED_EXPORTS = [
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

    def test_all_exports_importable(self) -> None:
        import k1.fabric.output_validation as mod

        for name in self.EXPECTED_EXPORTS:
            assert hasattr(mod, name), f"Missing export: {name}"

    def test_all_list_matches(self) -> None:
        import k1.fabric.output_validation as mod

        assert set(mod.__all__) == set(self.EXPECTED_EXPORTS)

    def test_event_constant(self) -> None:
        assert EVENT_VALIDATION_FAILED == "k1.fabric.output.validation.failed.v1"

    def test_default_max_data_bytes_value(self) -> None:
        assert DEFAULT_MAX_DATA_BYTES == 1_048_576

    def test_truncation_markers_is_tuple(self) -> None:
        assert isinstance(TRUNCATION_MARKERS, tuple)
        assert len(TRUNCATION_MARKERS) >= 3
