"""
M03 Tests: LLM Output Validator (Epic 4.1)
============================================

Tests for:
  - LLMOutputValidator construction from ToolSchema list
  - Tool allowlist validation
  - Required params validation
  - Param type spot-check
  - _attempt_fix: strips invalid calls
  - ValidationResult dataclass
  - Integration with ConciergeModelResponse
"""

from __future__ import annotations

from poc.k1_poc.llm.types import ConciergeModelResponse, FinishReason, ToolCallResult, ToolSchema
from poc.k1_poc.llm.validator import LLMOutputValidator, ValidationResult

# ===================================================================
# Test fixtures
# ===================================================================

ACKNOWLEDGE_SCHEMA = ToolSchema(
    name="acknowledge",
    description="Acknowledge the user's input.",
    parameters={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Ack message"},
        },
        "required": ["message"],
    },
    actor="front",
    category="signal",
)

UPDATE_BELIEFS_SCHEMA = ToolSchema(
    name="update_beliefs",
    description="Update user beliefs.",
    parameters={
        "type": "object",
        "properties": {
            "belief": {"type": "string", "description": "Belief text"},
            "confidence": {"type": "number", "description": "Confidence"},
        },
        "required": ["belief"],
    },
    actor="front",
    category="cognitive",
)

DISPATCH_TASK_SCHEMA = ToolSchema(
    name="dispatch_task",
    description="Dispatch a task to Back.",
    parameters={
        "type": "object",
        "properties": {
            "task_type": {"type": "string"},
            "intents": {"type": "array"},
            "tier": {"type": "string"},
        },
        "required": ["task_type", "intents"],
    },
    actor="front",
    category="action",
)

RECALL_MEMORY_SCHEMA = ToolSchema(
    name="recall_memory",
    description="Recall memory.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "count": {"type": "number"},
            "active": {"type": "boolean"},
            "tags": {"type": "array"},
            "metadata": {"type": "object"},
        },
        "required": ["query"],
    },
    actor="front",
    category="read",
)

FRONT_SCHEMAS = [
    ACKNOWLEDGE_SCHEMA,
    UPDATE_BELIEFS_SCHEMA,
    DISPATCH_TASK_SCHEMA,
    RECALL_MEMORY_SCHEMA,
]

BACK_INVOKE_SCHEMA = ToolSchema(
    name="invoke_capability",
    description="Invoke a capability.",
    parameters={
        "type": "object",
        "properties": {
            "capability": {"type": "string"},
            "args": {"type": "object"},
        },
        "required": ["capability"],
    },
    actor="back",
    category="action",
)

SUBMIT_RESULT_SCHEMA = ToolSchema(
    name="submit_result",
    description="Submit task result.",
    parameters={
        "type": "object",
        "properties": {
            "result_type": {"type": "string"},
            "final_answer": {"type": "string"},
        },
        "required": ["result_type"],
    },
    actor="back",
    category="control",
)

BACK_SCHEMAS = [BACK_INVOKE_SCHEMA, SUBMIT_RESULT_SCHEMA]


def _make_response(
    tool_calls: list[ToolCallResult] | None = None,
    text: str = "",
) -> ConciergeModelResponse:
    """Build a ConciergeModelResponse with tool calls."""
    return ConciergeModelResponse(
        text=text,
        tool_calls=tool_calls or [],
    )


# ===================================================================
# ValidationResult dataclass
# ===================================================================


class TestValidationResult:
    def test_valid_result(self):
        vr = ValidationResult(valid=True)
        assert vr.valid is True
        assert vr.issues == []
        assert vr.fixed_response is None

    def test_invalid_result(self):
        vr = ValidationResult(
            valid=False,
            issues=["Tool 'foo' not in allowlist"],
            fixed_response=None,
        )
        assert vr.valid is False
        assert len(vr.issues) == 1
        assert vr.fixed_response is None


# ===================================================================
# LLMOutputValidator construction
# ===================================================================


class TestValidatorConstruction:
    def test_builds_schema_lookup(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        assert v.has_schema("acknowledge")
        assert v.has_schema("update_beliefs")
        assert v.has_schema("dispatch_task")
        assert v.has_schema("recall_memory")
        assert not v.has_schema("hallucinated_tool")

    def test_schema_names(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        assert v.schema_names == {"acknowledge", "update_beliefs", "dispatch_task", "recall_memory"}

    def test_empty_schemas(self):
        v = LLMOutputValidator([])
        assert v.schema_names == set()

    def test_back_schemas(self):
        v = LLMOutputValidator(BACK_SCHEMAS)
        assert v.has_schema("invoke_capability")
        assert v.has_schema("submit_result")
        assert not v.has_schema("acknowledge")


# ===================================================================
# Tool allowlist validation
# ===================================================================


class TestToolAllowlist:
    def test_valid_tools_pass(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            tool_calls=[
                ToolCallResult(id="1", name="acknowledge", arguments={"message": "Got it"}),
                ToolCallResult(id="2", name="update_beliefs", arguments={"belief": "likes dogs"}),
            ]
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.valid is True

    def test_hallucinated_tool_fails(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            tool_calls=[
                ToolCallResult(id="1", name="acknowledge", arguments={"message": "Hi"}),
                ToolCallResult(id="2", name="hallucinated_tool", arguments={"x": 1}),
            ]
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.valid is False
        assert any("hallucinated_tool" in issue for issue in vr.issues)

    def test_all_hallucinated_no_fix(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            tool_calls=[
                ToolCallResult(id="1", name="fake_tool_1", arguments={}),
                ToolCallResult(id="2", name="fake_tool_2", arguments={}),
            ]
        )
        vr = v.validate(response, actor="back", iteration=0)
        assert vr.valid is False
        assert vr.fixed_response is None

    def test_mixed_valid_invalid_fixed(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            tool_calls=[
                ToolCallResult(id="1", name="acknowledge", arguments={"message": "Hi"}),
                ToolCallResult(id="2", name="hallucinated", arguments={}),
                ToolCallResult(id="3", name="update_beliefs", arguments={"belief": "test"}),
            ]
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.valid is False
        assert vr.fixed_response is not None
        # Fixed response keeps only valid calls
        assert len(vr.fixed_response.tool_calls) == 2
        names = [tc.name for tc in vr.fixed_response.tool_calls]
        assert "acknowledge" in names
        assert "update_beliefs" in names
        assert "hallucinated" not in names


# ===================================================================
# Required params validation
# ===================================================================


class TestRequiredParams:
    def test_all_required_present_passes(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            tool_calls=[
                ToolCallResult(id="1", name="acknowledge", arguments={"message": "Hi"}),
            ]
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.valid is True

    def test_missing_required_param_fails(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            tool_calls=[
                ToolCallResult(id="1", name="acknowledge", arguments={}),
            ]
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.valid is False
        assert any("missing required param" in issue.lower() for issue in vr.issues)

    def test_missing_required_stripped_in_fix(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            tool_calls=[
                ToolCallResult(id="1", name="acknowledge", arguments={"message": "Hi"}),
                ToolCallResult(id="2", name="update_beliefs", arguments={}),  # missing 'belief'
            ]
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.valid is False
        assert vr.fixed_response is not None
        assert len(vr.fixed_response.tool_calls) == 1
        assert vr.fixed_response.tool_calls[0].name == "acknowledge"

    def test_extra_params_allowed(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            tool_calls=[
                ToolCallResult(
                    id="1",
                    name="acknowledge",
                    arguments={"message": "Hi", "extra_param": True},
                ),
            ]
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.valid is True


# ===================================================================
# Param type spot-check
# ===================================================================


class TestParamTypeCheck:
    def test_correct_types_pass(self):
        v = LLMOutputValidator([RECALL_MEMORY_SCHEMA])
        response = _make_response(
            tool_calls=[
                ToolCallResult(
                    id="1",
                    name="recall_memory",
                    arguments={
                        "query": "test",
                        "count": 5,
                        "active": True,
                        "tags": ["a", "b"],
                        "metadata": {"key": "val"},
                    },
                ),
            ]
        )
        vr = v.validate(response, actor="front", iteration=1)
        assert vr.valid is True

    def test_string_param_gets_number_fails(self):
        v = LLMOutputValidator([RECALL_MEMORY_SCHEMA])
        response = _make_response(
            tool_calls=[
                ToolCallResult(
                    id="1",
                    name="recall_memory",
                    arguments={"query": 12345},  # should be string
                ),
            ]
        )
        vr = v.validate(response, actor="front", iteration=1)
        assert vr.valid is False
        assert any("expected string" in issue for issue in vr.issues)

    def test_number_param_gets_string_fails(self):
        v = LLMOutputValidator([RECALL_MEMORY_SCHEMA])
        response = _make_response(
            tool_calls=[
                ToolCallResult(
                    id="1",
                    name="recall_memory",
                    arguments={"query": "test", "count": "five"},
                ),
            ]
        )
        vr = v.validate(response, actor="front", iteration=1)
        assert vr.valid is False
        assert any("expected number" in issue for issue in vr.issues)

    def test_boolean_param_gets_string_fails(self):
        v = LLMOutputValidator([RECALL_MEMORY_SCHEMA])
        response = _make_response(
            tool_calls=[
                ToolCallResult(
                    id="1",
                    name="recall_memory",
                    arguments={"query": "test", "active": "yes"},
                ),
            ]
        )
        vr = v.validate(response, actor="front", iteration=1)
        assert vr.valid is False
        assert any("expected boolean" in issue for issue in vr.issues)

    def test_array_param_gets_string_fails(self):
        v = LLMOutputValidator([RECALL_MEMORY_SCHEMA])
        response = _make_response(
            tool_calls=[
                ToolCallResult(
                    id="1",
                    name="recall_memory",
                    arguments={"query": "test", "tags": "not_a_list"},
                ),
            ]
        )
        vr = v.validate(response, actor="front", iteration=1)
        assert vr.valid is False
        assert any("expected array" in issue for issue in vr.issues)

    def test_object_param_gets_string_fails(self):
        v = LLMOutputValidator([RECALL_MEMORY_SCHEMA])
        response = _make_response(
            tool_calls=[
                ToolCallResult(
                    id="1",
                    name="recall_memory",
                    arguments={"query": "test", "metadata": "not_an_object"},
                ),
            ]
        )
        vr = v.validate(response, actor="front", iteration=1)
        assert vr.valid is False
        assert any("expected object" in issue for issue in vr.issues)


# ===================================================================
# Text-only responses (no tool calls)
# ===================================================================


class TestTextOnlyResponse:
    def test_text_only_passes(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(text="Just a text response")
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.valid is True

    def test_empty_response_passes(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response()
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.valid is True


# ===================================================================
# Fixed response properties
# ===================================================================


class TestFixedResponse:
    def test_fixed_response_has_validation_fallback_reason(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            text="original text",
            tool_calls=[
                ToolCallResult(id="1", name="acknowledge", arguments={"message": "Hi"}),
                ToolCallResult(id="2", name="hallucinated", arguments={}),
            ],
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.fixed_response is not None
        assert vr.fixed_response.finish_reason == FinishReason.VALIDATION_FALLBACK

    def test_fixed_response_preserves_text(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            text="some text",
            tool_calls=[
                ToolCallResult(id="1", name="acknowledge", arguments={"message": "Hi"}),
                ToolCallResult(id="2", name="fake", arguments={}),
            ],
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.fixed_response is not None
        assert vr.fixed_response.text == "some text"

    def test_fixed_response_preserves_token_counts(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = ConciergeModelResponse(
            text="text",
            tool_calls=[
                ToolCallResult(id="1", name="acknowledge", arguments={"message": "Hi"}),
                ToolCallResult(id="2", name="fake", arguments={}),
            ],
            tokens_in=100,
            tokens_out=200,
            tokens_thoughts=50,
            latency_ms=150,
            model_id="test-model",
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.fixed_response is not None
        assert vr.fixed_response.tokens_in == 100
        assert vr.fixed_response.tokens_out == 200
        assert vr.fixed_response.tokens_thoughts == 50
        assert vr.fixed_response.latency_ms == 150
        assert vr.fixed_response.model_id == "test-model"


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    def test_schema_with_no_parameters(self):
        """ToolSchema with empty parameters should not require any params."""
        schema = ToolSchema(
            name="noop",
            description="No-op",
            parameters={},
        )
        v = LLMOutputValidator([schema])
        response = _make_response(
            tool_calls=[ToolCallResult(id="1", name="noop", arguments={"x": 1})],
        )
        vr = v.validate(response, actor="back", iteration=0)
        assert vr.valid is True

    def test_schema_with_none_parameters(self):
        """ToolSchema with empty dict parameters (guard against edge case)."""
        schema = ToolSchema(
            name="noop",
            description="No-op",
            parameters={},
        )
        v = LLMOutputValidator([schema])
        response = _make_response(
            tool_calls=[ToolCallResult(id="1", name="noop", arguments={})],
        )
        vr = v.validate(response, actor="back", iteration=0)
        assert vr.valid is True

    def test_multiple_issues_reported(self):
        v = LLMOutputValidator(FRONT_SCHEMAS)
        response = _make_response(
            tool_calls=[
                ToolCallResult(id="1", name="hallucinated_1", arguments={}),
                ToolCallResult(id="2", name="hallucinated_2", arguments={}),
                ToolCallResult(id="3", name="acknowledge", arguments={}),  # missing 'message'
            ]
        )
        vr = v.validate(response, actor="front", iteration=0)
        assert vr.valid is False
        # At least: acknowledge-first + 2 allowlist + 1 required param
        assert len(vr.issues) >= 3
