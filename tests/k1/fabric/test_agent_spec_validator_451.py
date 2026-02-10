"""
Unit tests for AgentSpecValidator -- Epic 6.2, Issue 4.5.1.

Tests all 7 validation rules for agent spec validation.
Uses real CapabilityRegistry (no mocks). TestPromptSystemAdapter for
prompt resolution.

References:
  - fabric-implementation-plan.md Epic 4.5, Issue 4.5.1
  - meta-agent-creation-integration-proposal.md
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.core.agent_builder import (
    AGENT_NAME_PATTERN,
    ALLOWED_CONTEXT_SECTIONS,
    MAX_EXECUTION_TIME_MS,
    MAX_LLM_BUDGET_TOKENS,
    MAX_TOOL_CALLS,
    MIN_EXECUTION_TIME_MS,
    MIN_LLM_BUDGET_TOKENS,
    MIN_TOOL_CALLS,
    AgentSpecValidationError,
    AgentSpecValidationResult,
    AgentSpecValidator,
)
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.types import Availability, CapabilityContract, SafetyBand

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def event_adapter() -> LocalEventAdapter:
    """LocalEventAdapter in capture mode."""
    return LocalEventAdapter(capture_mode=True)


@pytest.fixture()
def registry(event_adapter: LocalEventAdapter) -> CapabilityRegistry:
    """Real registry with validator + event port, pre-loaded with sample tools."""
    validator = ContractValidator()
    reg = CapabilityRegistry(validator=validator, event_port=event_adapter)  # type: ignore[arg-type]

    # Register tools that agents will reference
    reg.register(
        CapabilityContract(
            name="tool.execute.send_message",
            version="1.0.0",
            domain=["COMMUNICATION"],
            description="Send a message",
            capabilities=["send"],
            required_inputs=[],
            output={"type": "object"},
            provider_type="MCP",
            provider_id="mcp-messaging",
            safety_band_min=SafetyBand.GREEN.value,
            availability=Availability.ONLINE.value,
        )
    )
    reg.register(
        CapabilityContract(
            name="tool.read.check_vitals",
            version="1.0.0",
            domain=["HEALTH"],
            description="Check health vitals",
            capabilities=["vitals"],
            required_inputs=[],
            output={"type": "object"},
            provider_type="MCP",
            provider_id="mcp-health",
            safety_band_min=SafetyBand.GREEN.value,
            availability=Availability.ONLINE.value,
        )
    )
    reg.register(
        CapabilityContract(
            name="tool.execute.log_entry",
            version="1.0.0",
            domain=["LOGGING"],
            description="Log an entry",
            capabilities=["log"],
            required_inputs=[],
            output={"type": "object"},
            provider_type="MCP",
            provider_id="mcp-logging",
            safety_band_min=SafetyBand.GREEN.value,
            availability=Availability.ONLINE.value,
        )
    )
    return reg


@pytest.fixture()
def prompt_system() -> TestPromptSystemAdapter:
    """TestPromptSystemAdapter with sample templates."""
    ps = TestPromptSystemAdapter()
    ps.add_template(
        "health_summary_v1",
        "Summarize health data for {patient}",
        variables=["patient"],
    )
    ps.add_template(
        "generic_assistant_v1",
        "You are a helpful assistant",
        variables=[],
    )
    return ps


@pytest.fixture()
def validator(
    registry: CapabilityRegistry,
    prompt_system: TestPromptSystemAdapter,
) -> AgentSpecValidator:
    """AgentSpecValidator with real registry + prompt system."""
    return AgentSpecValidator(registry=registry, prompt_system=prompt_system)


@pytest.fixture()
def validator_no_prompt(registry: CapabilityRegistry) -> AgentSpecValidator:
    """AgentSpecValidator with real registry, no prompt system."""
    return AgentSpecValidator(registry=registry, prompt_system=None)


def _valid_spec(**overrides: Any) -> Dict[str, Any]:
    """Build a minimal valid agent spec with optional overrides."""
    spec: Dict[str, Any] = {
        "name": "agent.execute.test_helper",
        "tools_granted": ["tool.execute.send_message"],
        "required_context": ["beliefs_active", "interaction_history"],
        "prompt_template": "health_summary_v1",
        "domain": ["HEALTH"],
        "safety_band": "GREEN",
        "llm_budget_tokens": 8192,
        "max_tool_calls": 10,
        "max_execution_time_ms": 30000,
    }
    spec.update(overrides)
    return spec


# ===========================================================================
# Test: AgentSpecValidationResult dataclass
# ===========================================================================


class TestAgentSpecValidationResult:
    """Tests for the AgentSpecValidationResult frozen dataclass."""

    def test_default_is_valid(self) -> None:
        result = AgentSpecValidationResult()
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_custom_values(self) -> None:
        result = AgentSpecValidationResult(
            valid=False,
            errors=["error1", "error2"],
            warnings=["warn1"],
        )
        assert result.valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1

    def test_frozen(self) -> None:
        result = AgentSpecValidationResult()
        with pytest.raises(AttributeError):
            result.valid = False  # type: ignore[misc]


# ===========================================================================
# Test: AgentSpecValidationError exception
# ===========================================================================


class TestAgentSpecValidationError:
    """Tests for the AgentSpecValidationError exception."""

    def test_stores_errors(self) -> None:
        err = AgentSpecValidationError(["err1", "err2"])
        assert err.errors == ["err1", "err2"]
        assert "2 error(s)" in str(err)
        assert "err1" in str(err)

    def test_is_exception(self) -> None:
        err = AgentSpecValidationError(["something failed"])
        assert isinstance(err, Exception)

    def test_empty_errors(self) -> None:
        err = AgentSpecValidationError([])
        assert err.errors == []
        assert "0 error(s)" in str(err)


# ===========================================================================
# Test: Valid spec -- happy path
# ===========================================================================


class TestValidSpec:
    """A fully valid spec should pass all rules."""

    def test_valid_spec_passes(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec())
        assert result.valid is True
        assert result.errors == []

    def test_valid_spec_no_errors_on_validate_or_raise(self, validator: AgentSpecValidator) -> None:
        # Should not raise
        validator.validate_or_raise(_valid_spec())

    def test_valid_spec_minimal(self, validator: AgentSpecValidator) -> None:
        """Minimal spec: name + domain only."""
        result = validator.validate(
            {
                "name": "agent.execute.minimal",
                "domain": ["TEST"],
            }
        )
        assert result.valid is True

    def test_valid_spec_all_tools(self, validator: AgentSpecValidator) -> None:
        """Multiple valid tools."""
        result = validator.validate(
            _valid_spec(
                tools_granted=[
                    "tool.execute.send_message",
                    "tool.read.check_vitals",
                    "tool.execute.log_entry",
                ]
            )
        )
        assert result.valid is True

    def test_valid_spec_all_context_sections(self, validator: AgentSpecValidator) -> None:
        """All 6 allowed context sections."""
        result = validator.validate(_valid_spec(required_context=sorted(ALLOWED_CONTEXT_SECTIONS)))
        assert result.valid is True

    def test_valid_spec_each_safety_band(self, validator: AgentSpecValidator) -> None:
        """Each safety band value is valid."""
        for band in SafetyBand:
            result = validator.validate(_valid_spec(safety_band=band.value))
            assert result.valid is True, f"band={band.value} should be valid"

    def test_valid_spec_budget_boundaries(self, validator: AgentSpecValidator) -> None:
        """Budget at exact boundaries."""
        result = validator.validate(
            _valid_spec(
                llm_budget_tokens=MIN_LLM_BUDGET_TOKENS,
                max_tool_calls=MIN_TOOL_CALLS,
                max_execution_time_ms=MIN_EXECUTION_TIME_MS,
            )
        )
        assert result.valid is True

        result = validator.validate(
            _valid_spec(
                llm_budget_tokens=MAX_LLM_BUDGET_TOKENS,
                max_tool_calls=MAX_TOOL_CALLS,
                max_execution_time_ms=MAX_EXECUTION_TIME_MS,
            )
        )
        assert result.valid is True


# ===========================================================================
# Test: Rule 1 -- Name pattern
# ===========================================================================


class TestRule1NamePattern:
    """Rule 1: Name follows agent.execute.<identifier> pattern."""

    def test_missing_name(self, validator: AgentSpecValidator) -> None:
        spec = _valid_spec()
        del spec["name"]
        result = validator.validate(spec)
        assert not result.valid
        assert any("Missing required field: 'name'" in e for e in result.errors)

    def test_name_not_string(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(name=123))
        assert not result.valid
        assert any("must be a string" in e for e in result.errors)

    def test_name_wrong_prefix(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(name="tool.execute.something"))
        assert not result.valid
        assert any("must match pattern" in e for e in result.errors)

    def test_name_no_identifier(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(name="agent.execute."))
        assert not result.valid

    def test_name_uppercase(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(name="agent.execute.MyAgent"))
        assert not result.valid

    def test_name_starts_with_number(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(name="agent.execute.1invalid"))
        assert not result.valid

    def test_name_with_hyphen(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(name="agent.execute.my-agent"))
        assert not result.valid

    def test_name_valid_underscore(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(name="agent.execute.my_agent_v2"))
        assert result.valid

    def test_name_single_char(self, validator: AgentSpecValidator) -> None:
        """Minimum valid name: single letter + one more char."""
        result = validator.validate(_valid_spec(name="agent.execute.ab"))
        assert result.valid

    def test_name_single_letter_only(self, validator: AgentSpecValidator) -> None:
        """Single letter after prefix -- regex requires 2+ chars."""
        result = validator.validate(_valid_spec(name="agent.execute.a"))
        assert not result.valid

    def test_name_empty_string(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(name=""))
        assert not result.valid


# ===========================================================================
# Test: Rule 2 -- Tools granted
# ===========================================================================


class TestRule2ToolsGranted:
    """Rule 2: All tools_granted exist in registry."""

    def test_unknown_tool(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(tools_granted=["tool.execute.nonexistent"]))
        assert not result.valid
        assert any("Unknown tools" in e for e in result.errors)
        assert any("nonexistent" in e for e in result.errors)

    def test_multiple_unknown_tools(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(
            _valid_spec(tools_granted=["tool.execute.foo", "tool.execute.bar"])
        )
        assert not result.valid
        assert any("foo" in e for e in result.errors)
        assert any("bar" in e for e in result.errors)

    def test_mix_known_unknown(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(
            _valid_spec(tools_granted=["tool.execute.send_message", "tool.execute.fake"])
        )
        assert not result.valid
        assert any("fake" in e for e in result.errors)

    def test_empty_tools_list(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(tools_granted=[]))
        # Empty list is valid -- agent just has no tools
        assert result.valid

    def test_no_tools_granted_key(self, validator: AgentSpecValidator) -> None:
        spec = _valid_spec()
        del spec["tools_granted"]
        result = validator.validate(spec)
        # Missing tools_granted is valid with a warning
        assert result.valid
        assert any("No 'tools_granted'" in w for w in result.warnings)

    def test_tools_granted_not_list(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(tools_granted="not_a_list"))
        assert not result.valid
        assert any("must be a list" in e for e in result.errors)

    def test_tools_granted_non_string_item(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(tools_granted=[123]))
        assert not result.valid
        assert any("must be a string" in e for e in result.errors)


# ===========================================================================
# Test: Rule 3 -- Required context sections
# ===========================================================================


class TestRule3RequiredContext:
    """Rule 3: Required context sections from allowed set."""

    def test_invalid_section(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(
            _valid_spec(required_context=["beliefs_active", "nonexistent_section"])
        )
        assert not result.valid
        assert any("Invalid required_context" in e for e in result.errors)
        assert any("nonexistent_section" in e for e in result.errors)

    def test_no_required_context(self, validator: AgentSpecValidator) -> None:
        spec = _valid_spec()
        del spec["required_context"]
        result = validator.validate(spec)
        assert result.valid

    def test_empty_required_context(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(required_context=[]))
        assert result.valid

    def test_required_context_not_list(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(required_context="not_a_list"))
        assert not result.valid
        assert any("must be a list" in e for e in result.errors)

    def test_required_context_non_string_item(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(required_context=[42]))
        assert not result.valid
        assert any("must be a string" in e for e in result.errors)

    def test_each_allowed_section_individually(self, validator: AgentSpecValidator) -> None:
        """Each individual section is accepted."""
        for section in ALLOWED_CONTEXT_SECTIONS:
            result = validator.validate(_valid_spec(required_context=[section]))
            assert result.valid, f"Section '{section}' should be valid"


# ===========================================================================
# Test: Rule 4 -- Prompt template
# ===========================================================================


class TestRule4PromptTemplate:
    """Rule 4: Prompt template resolves via IPromptSystemPort."""

    def test_unknown_template(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(prompt_template="nonexistent_template_v99"))
        assert not result.valid
        assert any("not found via IPromptSystemPort" in e for e in result.errors)

    def test_valid_template(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(prompt_template="health_summary_v1"))
        assert result.valid

    def test_no_prompt_template(self, validator: AgentSpecValidator) -> None:
        spec = _valid_spec()
        del spec["prompt_template"]
        result = validator.validate(spec)
        assert result.valid

    def test_empty_prompt_template(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(prompt_template=""))
        assert result.valid

    def test_prompt_template_not_string(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(prompt_template=42))
        assert not result.valid
        assert any("must be a string" in e for e in result.errors)

    def test_no_prompt_system_configured(self, validator_no_prompt: AgentSpecValidator) -> None:
        """When no prompt system, validation skips with warning."""
        result = validator_no_prompt.validate(_valid_spec(prompt_template="anything"))
        assert result.valid  # Pass with warning, not error
        assert any("Cannot validate" in w for w in result.warnings)


# ===========================================================================
# Test: Rule 5 -- Domain tags
# ===========================================================================


class TestRule5Domain:
    """Rule 5: Domain tags non-empty and no duplicates."""

    def test_missing_domain(self, validator: AgentSpecValidator) -> None:
        spec = _valid_spec()
        del spec["domain"]
        result = validator.validate(spec)
        assert not result.valid
        assert any("Missing required field: 'domain'" in e for e in result.errors)

    def test_empty_domain(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(domain=[]))
        assert not result.valid
        assert any("at least one tag" in e for e in result.errors)

    def test_domain_not_list(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(domain="HEALTH"))
        assert not result.valid
        assert any("must be a list" in e for e in result.errors)

    def test_domain_non_string_tag(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(domain=[123]))
        assert not result.valid
        assert any("must be a string" in e for e in result.errors)

    def test_duplicate_domain_tags(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(domain=["HEALTH", "HEALTH"]))
        assert not result.valid
        assert any("Duplicate domain tags" in e for e in result.errors)

    def test_multiple_unique_domains(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(domain=["HEALTH", "WELLNESS", "FITNESS"]))
        assert result.valid

    def test_single_domain(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(domain=["TEST"]))
        assert result.valid


# ===========================================================================
# Test: Rule 6 -- Safety band
# ===========================================================================


class TestRule6SafetyBand:
    """Rule 6: Safety band is a valid SafetyBand enum value."""

    def test_invalid_band(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(safety_band="INVALID"))
        assert not result.valid
        assert any("Invalid safety_band" in e for e in result.errors)

    def test_band_not_string(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(safety_band=42))
        assert not result.valid
        assert any("must be a string" in e for e in result.errors)

    def test_no_safety_band(self, validator: AgentSpecValidator) -> None:
        """No safety_band or safety_band_min -> defaults to GREEN (no error)."""
        spec = _valid_spec()
        del spec["safety_band"]
        result = validator.validate(spec)
        assert result.valid

    def test_safety_band_min_alias(self, validator: AgentSpecValidator) -> None:
        """Accept safety_band_min as alias."""
        spec = _valid_spec()
        del spec["safety_band"]
        spec["safety_band_min"] = "AMBER"
        result = validator.validate(spec)
        assert result.valid

    def test_safety_band_min_invalid(self, validator: AgentSpecValidator) -> None:
        spec = _valid_spec()
        del spec["safety_band"]
        spec["safety_band_min"] = "BOGUS"
        result = validator.validate(spec)
        assert not result.valid

    def test_all_valid_bands(self, validator: AgentSpecValidator) -> None:
        for band in ["GREEN", "AMBER", "RED", "CRISIS"]:
            result = validator.validate(_valid_spec(safety_band=band))
            assert result.valid, f"Band '{band}' should be valid"


# ===========================================================================
# Test: Rule 7 -- Budget ranges
# ===========================================================================


class TestRule7Budgets:
    """Rule 7: Budget ranges within constraints."""

    # --- llm_budget_tokens ---

    def test_tokens_below_min(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(llm_budget_tokens=MIN_LLM_BUDGET_TOKENS - 1))
        assert not result.valid
        assert any("llm_budget_tokens" in e for e in result.errors)

    def test_tokens_above_max(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(llm_budget_tokens=MAX_LLM_BUDGET_TOKENS + 1))
        assert not result.valid

    def test_tokens_at_min(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(llm_budget_tokens=MIN_LLM_BUDGET_TOKENS))
        assert result.valid

    def test_tokens_at_max(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(llm_budget_tokens=MAX_LLM_BUDGET_TOKENS))
        assert result.valid

    def test_tokens_not_int(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(llm_budget_tokens="many"))
        assert not result.valid

    def test_no_tokens(self, validator: AgentSpecValidator) -> None:
        spec = _valid_spec()
        del spec["llm_budget_tokens"]
        result = validator.validate(spec)
        assert result.valid

    # --- max_tool_calls ---

    def test_calls_below_min(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(max_tool_calls=MIN_TOOL_CALLS - 1))
        assert not result.valid

    def test_calls_above_max(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(max_tool_calls=MAX_TOOL_CALLS + 1))
        assert not result.valid

    def test_calls_at_min(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(max_tool_calls=MIN_TOOL_CALLS))
        assert result.valid

    def test_calls_at_max(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(max_tool_calls=MAX_TOOL_CALLS))
        assert result.valid

    def test_calls_not_int(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(max_tool_calls="five"))
        assert not result.valid

    def test_no_calls(self, validator: AgentSpecValidator) -> None:
        spec = _valid_spec()
        del spec["max_tool_calls"]
        result = validator.validate(spec)
        assert result.valid

    # --- max_execution_time_ms ---

    def test_time_below_min(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(max_execution_time_ms=MIN_EXECUTION_TIME_MS - 1))
        assert not result.valid

    def test_time_above_max(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(max_execution_time_ms=MAX_EXECUTION_TIME_MS + 1))
        assert not result.valid

    def test_time_at_min(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(max_execution_time_ms=MIN_EXECUTION_TIME_MS))
        assert result.valid

    def test_time_at_max(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(max_execution_time_ms=MAX_EXECUTION_TIME_MS))
        assert result.valid

    def test_time_not_int(self, validator: AgentSpecValidator) -> None:
        result = validator.validate(_valid_spec(max_execution_time_ms="slow"))
        assert not result.valid

    def test_no_time(self, validator: AgentSpecValidator) -> None:
        spec = _valid_spec()
        del spec["max_execution_time_ms"]
        result = validator.validate(spec)
        assert result.valid


# ===========================================================================
# Test: validate_or_raise
# ===========================================================================


class TestValidateOrRaise:
    """Tests for validate_or_raise() -- raises on failure."""

    def test_raises_on_invalid(self, validator: AgentSpecValidator) -> None:
        with pytest.raises(AgentSpecValidationError) as exc_info:
            validator.validate_or_raise(_valid_spec(name="INVALID"))
        assert len(exc_info.value.errors) > 0

    def test_no_raise_on_valid(self, validator: AgentSpecValidator) -> None:
        validator.validate_or_raise(_valid_spec())

    def test_error_contains_all_failures(self, validator: AgentSpecValidator) -> None:
        """Spec with multiple rule violations should report all errors."""
        spec = {
            "name": "INVALID",
            "tools_granted": ["tool.execute.nonexistent"],
            "required_context": ["invalid_section"],
            "domain": [],
            "safety_band": "BOGUS",
            "llm_budget_tokens": -1,
        }
        with pytest.raises(AgentSpecValidationError) as exc_info:
            validator.validate_or_raise(spec)
        errors = exc_info.value.errors
        # Should have errors from rules 1, 2, 3, 5, 6, 7
        assert len(errors) >= 5


# ===========================================================================
# Test: Multiple rule violations at once
# ===========================================================================


class TestMultipleViolations:
    """A single spec can violate multiple rules simultaneously."""

    def test_all_rules_violated(self, validator: AgentSpecValidator) -> None:
        spec = {
            "name": "BOGUS",
            "tools_granted": ["nonexistent_tool"],
            "required_context": ["invalid_section"],
            "prompt_template": "nonexistent_prompt",
            "domain": [],
            "safety_band": "INVALID_BAND",
            "llm_budget_tokens": 0,
            "max_tool_calls": 999,
            "max_execution_time_ms": 0,
        }
        result = validator.validate(spec)
        assert not result.valid
        # At least one error per violated rule
        assert len(result.errors) >= 7

    def test_errors_are_specific(self, validator: AgentSpecValidator) -> None:
        """Each error message identifies the failing rule."""
        spec = {
            "name": 42,
            "domain": "not_a_list",
            "safety_band": 99,
            "llm_budget_tokens": "many",
        }
        result = validator.validate(spec)
        assert not result.valid
        error_text = " ".join(result.errors)
        assert "name" in error_text.lower()
        assert "domain" in error_text.lower()
        assert "safety_band" in error_text.lower()
        assert "llm_budget_tokens" in error_text.lower()


# ===========================================================================
# Test: Thread safety / statelessness
# ===========================================================================


class TestStatelessness:
    """Validator is stateless -- concurrent calls do not interfere."""

    def test_independent_calls(self, validator: AgentSpecValidator) -> None:
        """Multiple validate() calls are independent."""
        result1 = validator.validate(_valid_spec())
        result2 = validator.validate(_valid_spec(name="INVALID"))
        result3 = validator.validate(_valid_spec())

        assert result1.valid is True
        assert result2.valid is False
        assert result3.valid is True

    def test_validate_or_raise_does_not_mutate(self, validator: AgentSpecValidator) -> None:
        """validate_or_raise does not affect subsequent calls."""
        with pytest.raises(AgentSpecValidationError):
            validator.validate_or_raise(_valid_spec(name="BAD"))
        # Subsequent call should work fine
        validator.validate_or_raise(_valid_spec())


# ===========================================================================
# Test: Constants
# ===========================================================================


class TestConstants:
    """Verify exported constants match plan spec."""

    def test_agent_name_pattern(self) -> None:
        assert AGENT_NAME_PATTERN.match("agent.execute.test_agent")
        assert not AGENT_NAME_PATTERN.match("tool.execute.test_tool")
        assert not AGENT_NAME_PATTERN.match("agent.execute.")

    def test_allowed_context_sections(self) -> None:
        assert "beliefs_active" in ALLOWED_CONTEXT_SECTIONS
        assert "interaction_history" in ALLOWED_CONTEXT_SECTIONS
        assert "task_context" in ALLOWED_CONTEXT_SECTIONS
        assert "rhythm_state" in ALLOWED_CONTEXT_SECTIONS
        assert "active_plans" in ALLOWED_CONTEXT_SECTIONS
        assert "pending_clarifications" in ALLOWED_CONTEXT_SECTIONS
        assert len(ALLOWED_CONTEXT_SECTIONS) == 6

    def test_budget_constants(self) -> None:
        assert MIN_LLM_BUDGET_TOKENS == 512
        assert MAX_LLM_BUDGET_TOKENS == 32768
        assert MIN_TOOL_CALLS == 1
        assert MAX_TOOL_CALLS == 50
        assert MIN_EXECUTION_TIME_MS == 1000
        assert MAX_EXECUTION_TIME_MS == 60000


# ===========================================================================
# Test: Repr
# ===========================================================================


class TestRepr:
    """AgentSpecValidator repr."""

    def test_repr(self, validator: AgentSpecValidator) -> None:
        r = repr(validator)
        assert "AgentSpecValidator" in r
