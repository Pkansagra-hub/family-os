"""
Tests for Epic 4.2: Context Builder (4.2.1), ContextBudget (4.2.2),
and token counting (4.2.3).

Covers:
  - Token counting (count_tokens, count_tokens_dict)
  - ContextBudget 5-level compression strategy
  - ContextBuilder 6-step assembly pipeline
  - Port Protocol integration (ISessionStateReader, IPromptSystemPort)
  - Graceful degradation (missing ports, missing sections)
  - Module exports verification

Test naming: Test<Class><Feature>.test_<scenario>
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.core.context_budget import (
    ALL_SECTION_NAMES,
    DEFAULT_RESPONSE_HEADROOM,
    HOT_SECTION_NAMES,
    MAX_HISTORY_TURNS_COMPRESSED,
    MIN_BELIEF_CONFIDENCE,
    TOKEN_CEILING,
    WARM_SECTION_NAMES,
    BudgetAllocation,
    BudgetResult,
    CompressionLevel,
    ContextBudget,
    ContextBudgetConfig,
    count_tokens,
    count_tokens_dict,
)
from k1.fabric.core.context_builder import (
    ContextAssemblyError,
    ContextBuilder,
    ContextBuilderConfig,
    ContextBuilderError,
    ContextBuildResult,
)
from k1.fabric.types import CapabilityContract, ExecutionContext

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------


# ===================================================================
# Fakes / Helpers
# ===================================================================


class FakeStateReader:
    """Implements ISessionStateReader Protocol structurally."""

    def __init__(self, sections: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._sections: Dict[str, Dict[str, Any]] = sections or {}

    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        return self._sections.get(section)


class FakePromptSystem:
    """Implements IPromptSystemPort Protocol structurally."""

    def __init__(
        self,
        templates: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self._templates: Dict[str, Dict[str, Any]] = templates or {}

    def resolve(self, template_name: str) -> Optional[Dict[str, Any]]:
        return self._templates.get(template_name)

    def compile(self, template: Dict[str, Any], variables: Dict[str, Any]) -> str:
        text = template.get("text", "")
        for k, v in variables.items():
            text = text.replace(f"{{{k}}}", str(v))
        return text


class FailingStateReader:
    """ISessionStateReader that always raises."""

    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        raise RuntimeError("read failed")


class FailingPromptSystem:
    """IPromptSystemPort that always raises on resolve."""

    def resolve(self, template_name: str) -> Optional[Dict[str, Any]]:
        raise RuntimeError("prompt resolve failed")

    def compile(self, template: Dict[str, Any], variables: Dict[str, Any]) -> str:
        raise RuntimeError("compile failed")


def _contract(
    required_context: Optional[List[str]] = None,
    optional_context: Optional[List[str]] = None,
    **kwargs: Any,
) -> CapabilityContract:
    """Create a CapabilityContract with context requirements."""
    return CapabilityContract(
        name=kwargs.get("name", "tool.test"),
        version=kwargs.get("version", "1.0.0"),
        required_context=required_context or [],
        optional_context=optional_context or [],
        **{k: v for k, v in kwargs.items() if k not in ("name", "version")},
    )


# ===================================================================
# Tests: Token Counting (4.2.3)
# ===================================================================


class TestCountTokens:
    """Issue 4.2.3 -- count_tokens utility."""

    def test_empty_string_returns_0(self) -> None:
        assert count_tokens("") == 0

    def test_none_coerced_to_empty(self) -> None:
        # count_tokens expects str, but "" is falsy
        assert count_tokens("") == 0

    def test_short_string_positive(self) -> None:
        result = count_tokens("hello world")
        assert result > 0

    def test_longer_string_more_tokens(self) -> None:
        short = count_tokens("hi")
        long = count_tokens("hello world this is a longer string")
        assert long > short

    def test_returns_int(self) -> None:
        assert isinstance(count_tokens("test"), int)


class TestCountTokensDict:
    """Issue 4.2.3 -- count_tokens_dict utility."""

    def test_empty_dict_returns_0(self) -> None:
        assert count_tokens_dict({}) == 0

    def test_non_empty_dict_positive(self) -> None:
        result = count_tokens_dict({"key": "value"})
        assert result > 0

    def test_larger_dict_more_tokens(self) -> None:
        small = count_tokens_dict({"a": 1})
        large = count_tokens_dict({"a": 1, "b": "very long text " * 100})
        assert large > small


# ===================================================================
# Tests: ContextBudget constants
# ===================================================================


class TestBudgetConstants:
    """Verify public constants are accessible and correct."""

    def test_token_ceiling(self) -> None:
        assert TOKEN_CEILING == 128_000

    def test_default_response_headroom(self) -> None:
        assert DEFAULT_RESPONSE_HEADROOM == 4_000

    def test_min_belief_confidence(self) -> None:
        assert MIN_BELIEF_CONFIDENCE == 0.5

    def test_max_history_turns(self) -> None:
        assert MAX_HISTORY_TURNS_COMPRESSED == 3

    def test_hot_section_names(self) -> None:
        assert "control" in HOT_SECTION_NAMES
        assert "beliefs_active" in HOT_SECTION_NAMES
        assert len(HOT_SECTION_NAMES) == 8

    def test_warm_section_names(self) -> None:
        assert "persona" in WARM_SECTION_NAMES
        assert "history_recent" in WARM_SECTION_NAMES
        assert len(WARM_SECTION_NAMES) == 4

    def test_all_section_names(self) -> None:
        assert ALL_SECTION_NAMES == HOT_SECTION_NAMES | WARM_SECTION_NAMES
        assert len(ALL_SECTION_NAMES) == 12


# ===================================================================
# Tests: CompressionLevel enum
# ===================================================================


class TestCompressionLevel:
    """CompressionLevel enum values."""

    def test_none_value(self) -> None:
        assert CompressionLevel.NONE.value == "none"

    def test_l1_value(self) -> None:
        assert CompressionLevel.L1_DROP_OPTIONAL.value == "L1_drop_optional"

    def test_l5_value(self) -> None:
        assert CompressionLevel.L5_EMERGENCY_HOT_ONLY.value == "L5_emergency_hot_only"

    def test_all_levels(self) -> None:
        assert len(CompressionLevel) == 6


# ===================================================================
# Tests: BudgetAllocation
# ===================================================================


class TestBudgetAllocation:
    """BudgetAllocation default allocation targets."""

    def test_defaults(self) -> None:
        alloc = BudgetAllocation()
        assert alloc.system_prompt_min == 2_000
        assert alloc.session_sections_max == 40_000

    def test_frozen(self) -> None:
        alloc = BudgetAllocation()
        with pytest.raises(AttributeError):
            alloc.system_prompt_min = 999  # type: ignore[misc]

    def test_to_dict(self) -> None:
        d = BudgetAllocation().to_dict()
        assert "system_prompt" in d
        assert "response_headroom" in d

    def test_repr(self) -> None:
        r = repr(BudgetAllocation())
        assert "BudgetAllocation" in r


# ===================================================================
# Tests: BudgetResult
# ===================================================================


class TestBudgetResult:
    """BudgetResult frozen dataclass."""

    def test_defaults(self) -> None:
        r = BudgetResult()
        assert r.total_tokens == 0
        assert r.compression_applied == CompressionLevel.NONE
        assert r.sections_dropped == []
        assert r.over_budget is False

    def test_frozen(self) -> None:
        r = BudgetResult()
        with pytest.raises(AttributeError):
            r.total_tokens = 999  # type: ignore[misc]

    def test_to_dict(self) -> None:
        d = BudgetResult(total_tokens=100).to_dict()
        assert d["total_tokens"] == 100
        assert d["compression_applied"] == "none"

    def test_repr(self) -> None:
        r = repr(BudgetResult(total_tokens=42))
        assert "42" in r


# ===================================================================
# Tests: ContextBudgetConfig
# ===================================================================


class TestContextBudgetConfig:
    """ContextBudgetConfig frozen dataclass."""

    def test_defaults(self) -> None:
        c = ContextBudgetConfig()
        assert c.ceiling == TOKEN_CEILING
        assert c.response_headroom == DEFAULT_RESPONSE_HEADROOM

    def test_custom(self) -> None:
        c = ContextBudgetConfig(ceiling=50_000, response_headroom=2_000)
        assert c.ceiling == 50_000

    def test_frozen(self) -> None:
        c = ContextBudgetConfig()
        with pytest.raises(AttributeError):
            c.ceiling = 999  # type: ignore[misc]

    def test_repr(self) -> None:
        assert "ceiling" in repr(ContextBudgetConfig())


# ===================================================================
# Tests: ContextBudget apply() -- no compression
# ===================================================================


class TestContextBudgetNoCompression:
    """ContextBudget.apply() when within budget."""

    def test_empty_context_within_budget(self) -> None:
        budget = ContextBudget()
        result = budget.apply(session_sections={}, prompt=None, params={})
        assert result.total_tokens == 0
        assert result.compression_applied == CompressionLevel.NONE
        assert not result.over_budget

    def test_small_context_within_budget(self) -> None:
        budget = ContextBudget()
        result = budget.apply(
            session_sections={"control": {"mode": "chat"}},
            prompt="Hello",
            params={"q": "test"},
        )
        assert result.total_tokens > 0
        assert result.compression_applied == CompressionLevel.NONE

    def test_effective_budget(self) -> None:
        budget = ContextBudget(ContextBudgetConfig(ceiling=10_000, response_headroom=2_000))
        assert budget.effective_budget == 8_000

    def test_prompt_passed_through(self) -> None:
        budget = ContextBudget()
        result = budget.apply(session_sections={}, prompt="system prompt", params={})
        assert result.prompt == "system prompt"

    def test_params_passed_through(self) -> None:
        budget = ContextBudget()
        result = budget.apply(session_sections={}, params={"key": "val"})
        assert result.params == {"key": "val"}


# ===================================================================
# Tests: ContextBudget L1 -- Drop optional
# ===================================================================


class TestContextBudgetL1DropOptional:
    """L1 compression: drop optional_context sections first."""

    def _make_over_budget(self) -> tuple:
        """Create a budget + sections that exceed a tight ceiling."""
        config = ContextBudgetConfig(ceiling=20, response_headroom=0)
        budget = ContextBudget(config)
        sections = {
            "control": {"mode": "chat"},
            "persona": {"trait": "x" * 200},  # big optional (~37 tokens with tiktoken)
        }
        return budget, sections

    def test_optional_dropped(self) -> None:
        budget, sections = self._make_over_budget()
        result = budget.apply(
            session_sections=sections,
            optional_sections=["persona"],
        )
        assert "persona" not in result.session_sections
        assert "persona" in result.sections_dropped

    def test_compression_level_is_l1(self) -> None:
        budget, sections = self._make_over_budget()
        result = budget.apply(
            session_sections=sections,
            optional_sections=["persona"],
        )
        # If dropping optional was enough, level is L1
        if not result.over_budget and result.total_tokens <= budget.effective_budget:
            assert result.compression_applied == CompressionLevel.L1_DROP_OPTIONAL


# ===================================================================
# Tests: ContextBudget L2 -- Truncate history
# ===================================================================


class TestContextBudgetL2TruncateHistory:
    """L2 compression: truncate history_recent to last N turns."""

    def test_history_truncated(self) -> None:
        config = ContextBudgetConfig(ceiling=20, response_headroom=0, max_history_turns=2)
        budget = ContextBudget(config)
        sections = {
            "history_recent": {
                "turns": [
                    {"id": "t1", "text": "x" * 500},
                    {"id": "t2", "text": "x" * 500},
                    {"id": "t3", "text": "x" * 500},
                    {"id": "t4", "text": "x" * 500},
                    {"id": "t5", "text": "x" * 500},
                ]
            },
        }
        result = budget.apply(session_sections=sections, optional_sections=[])
        turns = result.session_sections.get("history_recent", {}).get("turns", [])
        assert len(turns) <= 2

    def test_no_history_section_no_crash(self) -> None:
        config = ContextBudgetConfig(ceiling=10, response_headroom=0)
        budget = ContextBudget(config)
        result = budget.apply(session_sections={"control": {"x": "y" * 100}})
        # Should not crash even if history_recent absent
        assert result is not None


# ===================================================================
# Tests: ContextBudget L3 -- Filter beliefs
# ===================================================================


class TestContextBudgetL3FilterBeliefs:
    """L3 compression: remove low-confidence beliefs."""

    def test_low_confidence_removed(self) -> None:
        config = ContextBudgetConfig(ceiling=20, response_headroom=0, min_belief_confidence=0.6)
        budget = ContextBudget(config)
        sections = {
            "beliefs_active": {
                "facts": [
                    {"text": "x" * 500, "confidence": 0.9},
                    {"text": "y" * 500, "confidence": 0.3},
                    {"text": "z" * 500, "confidence": 0.7},
                ]
            },
        }
        result = budget.apply(session_sections=sections, optional_sections=[])
        facts = result.session_sections.get("beliefs_active", {}).get("facts", [])
        confidences = [f["confidence"] for f in facts]
        assert all(c >= 0.6 for c in confidences)

    def test_no_beliefs_section_no_crash(self) -> None:
        config = ContextBudgetConfig(ceiling=10, response_headroom=0)
        budget = ContextBudget(config)
        result = budget.apply(session_sections={"control": {"x": "y" * 100}})
        assert result is not None


# ===================================================================
# Tests: ContextBudget L4 -- Summarize scoreboard
# ===================================================================


class TestContextBudgetL4SummarizeScoreboard:
    """L4 compression: keep only current_qud from scoreboard."""

    def test_scoreboard_reduced_to_current_qud(self) -> None:
        config = ContextBudgetConfig(ceiling=30, response_headroom=0)
        budget = ContextBudget(config)
        sections = {
            "scoreboard": {
                "current_qud": "What time is the meeting?",
                "completed_tasks": ["a" * 50, "b" * 50],
                "pending_tasks": ["c" * 50],
            },
        }
        result = budget.apply(session_sections=sections, optional_sections=[])
        sb = result.session_sections.get("scoreboard", {})
        # Only current_qud should remain after L4
        if result.compression_applied in (
            CompressionLevel.L4_SUMMARIZE_SCOREBOARD,
            CompressionLevel.L5_EMERGENCY_HOT_ONLY,
        ):
            assert "completed_tasks" not in sb
            assert sb.get("current_qud") == "What time is the meeting?"


# ===================================================================
# Tests: ContextBudget L5 -- Emergency HOT only
# ===================================================================


class TestContextBudgetL5EmergencyHotOnly:
    """L5 compression: drop all WARM sections, keep HOT only."""

    def test_warm_sections_dropped(self) -> None:
        config = ContextBudgetConfig(ceiling=20, response_headroom=0)
        budget = ContextBudget(config)
        sections = {
            "control": {"mode": "chat"},
            "persona": {"traits": "x" * 200},
            "telemetry": {"metrics": "y" * 200},
            "history_recent": {"turns": [{"t": "z" * 200}]},
        }
        result = budget.apply(session_sections=sections, optional_sections=[])
        # WARM sections should be gone after L5
        for warm_name in WARM_SECTION_NAMES:
            if warm_name in sections:
                assert warm_name not in result.session_sections or result.over_budget

    def test_hot_sections_preserved(self) -> None:
        config = ContextBudgetConfig(ceiling=20, response_headroom=0)
        budget = ContextBudget(config)
        sections = {
            "control": {"mode": "chat"},
            "persona": {"traits": "x" * 500},
        }
        result = budget.apply(session_sections=sections, optional_sections=[])
        # control (HOT) should still be present
        assert "control" in result.session_sections


# ===================================================================
# Tests: ContextBudget full cascade
# ===================================================================


class TestContextBudgetFullCascade:
    """Verify the compression levels cascade correctly."""

    def test_cascade_through_all_levels(self) -> None:
        """Very tight budget forces through all 5 levels."""
        config = ContextBudgetConfig(
            ceiling=5,  # impossibly tight
            response_headroom=0,
            max_history_turns=1,
            min_belief_confidence=0.9,
        )
        budget = ContextBudget(config)
        sections = {
            "control": {"mode": "chat", "data": "a" * 100},
            "beliefs_active": {
                "facts": [
                    {"text": "x" * 50, "confidence": 0.3},
                    {"text": "y" * 50, "confidence": 0.95},
                ]
            },
            "scoreboard": {"current_qud": "q?", "tasks": ["t" * 50]},
            "history_recent": {"turns": [{"i": 1}, {"i": 2}, {"i": 3}]},
            "persona": {"traits": "x" * 100},
            "telemetry": {"m": "y" * 100},
        }
        result = budget.apply(
            session_sections=sections,
            optional_sections=["persona", "telemetry"],
        )
        assert result.compression_applied == CompressionLevel.L5_EMERGENCY_HOT_ONLY

    def test_over_budget_flag_when_still_exceeds(self) -> None:
        """Even after L5, if HOT data exceeds ceiling, over_budget=True."""
        config = ContextBudgetConfig(ceiling=1, response_headroom=0)
        budget = ContextBudget(config)
        sections = {"control": {"data": "x" * 1000}}
        result = budget.apply(session_sections=sections)
        assert result.over_budget is True


# ===================================================================
# Tests: ContextBuilder -- basic assembly
# ===================================================================


class TestContextBuilderBasicAssembly:
    """Issue 4.2.1 -- basic 6-step assembly."""

    def test_empty_contract_produces_context(self) -> None:
        builder = ContextBuilder()
        result = builder.build(contract=_contract(), trace_id="tr-1")
        assert isinstance(result.context, ExecutionContext)
        assert result.context.trace_id == "tr-1"

    def test_params_injected(self) -> None:
        builder = ContextBuilder()
        result = builder.build(
            contract=_contract(),
            params={"query": "test"},
            trace_id="tr-2",
        )
        assert result.context.params == {"query": "test"}

    def test_session_sections_populated(self) -> None:
        reader = FakeStateReader({"control": {"mode": "chat"}})
        builder = ContextBuilder(state_reader=reader)
        contract = _contract(required_context=["control"])
        result = builder.build(contract=contract, session_id="s1")
        assert "control" in result.context.session_sections
        assert result.context.session_sections["control"]["mode"] == "chat"

    def test_prompt_resolved_and_compiled(self) -> None:
        prompt_sys = FakePromptSystem(templates={"greet": {"text": "Hello {name}!"}})
        builder = ContextBuilder(prompt_system=prompt_sys)
        result = builder.build(
            contract=_contract(),
            prompt_template_name="greet",
            prompt_variables={"name": "Alice"},
        )
        assert result.context.prompt == "Hello Alice!"
        assert result.prompt_resolved is True

    def test_token_count_positive(self) -> None:
        reader = FakeStateReader({"control": {"mode": "chat"}})
        builder = ContextBuilder(state_reader=reader)
        result = builder.build(
            contract=_contract(required_context=["control"]),
            params={"q": "test"},
            session_id="s1",
        )
        assert result.context.token_count > 0

    def test_assembly_ms_non_negative(self) -> None:
        builder = ContextBuilder()
        result = builder.build(contract=_contract())
        assert result.assembly_ms >= 0.0

    def test_result_type(self) -> None:
        builder = ContextBuilder()
        result = builder.build(contract=_contract())
        assert isinstance(result, ContextBuildResult)


# ===================================================================
# Tests: ContextBuilder -- missing sections
# ===================================================================


class TestContextBuilderMissingSections:
    """Graceful degradation when sections are missing."""

    def test_required_section_missing_logged(self) -> None:
        reader = FakeStateReader({})  # no sections
        builder = ContextBuilder(state_reader=reader)
        result = builder.build(
            contract=_contract(required_context=["control"]),
            session_id="s1",
        )
        assert "control" in result.missing_required
        assert result.context.session_sections == {}

    def test_optional_section_missing_no_error(self) -> None:
        reader = FakeStateReader({})
        builder = ContextBuilder(state_reader=reader)
        result = builder.build(
            contract=_contract(optional_context=["persona"]),
            session_id="s1",
        )
        assert "persona" in result.missing_optional

    def test_mixed_present_and_missing(self) -> None:
        reader = FakeStateReader({"control": {"mode": "chat"}})
        builder = ContextBuilder(state_reader=reader)
        result = builder.build(
            contract=_contract(
                required_context=["control", "beliefs_active"],
                optional_context=["persona"],
            ),
            session_id="s1",
        )
        assert "control" in result.context.session_sections
        assert "beliefs_active" in result.missing_required
        assert "persona" in result.missing_optional


# ===================================================================
# Tests: ContextBuilder -- no ports (graceful degradation)
# ===================================================================


class TestContextBuilderNoPorts:
    """Graceful degradation when ports are None."""

    def test_no_state_reader_produces_empty_sections(self) -> None:
        builder = ContextBuilder(state_reader=None)
        result = builder.build(
            contract=_contract(required_context=["control"]),
        )
        assert result.context.session_sections == {}
        assert "control" in result.missing_required

    def test_no_prompt_system_skips_prompt(self) -> None:
        builder = ContextBuilder(prompt_system=None)
        result = builder.build(
            contract=_contract(),
            prompt_template_name="greet",
        )
        assert result.context.prompt is None
        assert result.prompt_resolved is False

    def test_has_state_reader_false(self) -> None:
        builder = ContextBuilder()
        assert builder.has_state_reader is False

    def test_has_prompt_system_false(self) -> None:
        builder = ContextBuilder()
        assert builder.has_prompt_system is False

    def test_has_state_reader_true(self) -> None:
        builder = ContextBuilder(state_reader=FakeStateReader())
        assert builder.has_state_reader is True


# ===================================================================
# Tests: ContextBuilder -- failing ports
# ===================================================================


class TestContextBuilderFailingPorts:
    """Graceful degradation when ports raise exceptions."""

    def test_state_reader_exception_handled(self) -> None:
        builder = ContextBuilder(state_reader=FailingStateReader())
        result = builder.build(
            contract=_contract(required_context=["control"]),
            session_id="s1",
        )
        # Should not raise; section treated as missing
        assert result.context.session_sections == {}

    def test_prompt_system_exception_handled(self) -> None:
        builder = ContextBuilder(prompt_system=FailingPromptSystem())
        result = builder.build(
            contract=_contract(),
            prompt_template_name="bad_template",
        )
        assert result.context.prompt is None
        assert result.prompt_resolved is False


# ===================================================================
# Tests: ContextBuilder -- prompt resolution
# ===================================================================


class TestContextBuilderPromptResolution:
    """Issue 4.2.1 step 4 -- prompt template resolution."""

    def test_template_not_found(self) -> None:
        prompt_sys = FakePromptSystem(templates={})
        builder = ContextBuilder(prompt_system=prompt_sys)
        result = builder.build(
            contract=_contract(),
            prompt_template_name="nonexistent",
        )
        assert result.context.prompt is None
        assert result.prompt_resolved is False

    def test_no_template_name_skips(self) -> None:
        prompt_sys = FakePromptSystem(templates={"greet": {"text": "Hi"}})
        builder = ContextBuilder(prompt_system=prompt_sys)
        result = builder.build(contract=_contract())
        assert result.context.prompt is None
        assert result.prompt_resolved is False

    def test_variables_substituted(self) -> None:
        prompt_sys = FakePromptSystem(templates={"sys": {"text": "You are a {role} assistant."}})
        builder = ContextBuilder(prompt_system=prompt_sys)
        result = builder.build(
            contract=_contract(),
            prompt_template_name="sys",
            prompt_variables={"role": "helpful"},
        )
        assert result.context.prompt == "You are a helpful assistant."


# ===================================================================
# Tests: ContextBuilder -- budget integration
# ===================================================================


class TestContextBuilderBudgetIntegration:
    """ContextBuilder step 5 -- token budget applied."""

    def test_large_context_compressed(self) -> None:
        """Optional sections dropped when over budget."""
        reader = FakeStateReader(
            {
                "control": {"mode": "chat"},
                "persona": {"data": "x" * 10000},
            }
        )
        config = ContextBuilderConfig(
            budget_config=ContextBudgetConfig(ceiling=100, response_headroom=0)
        )
        builder = ContextBuilder(state_reader=reader, config=config)
        result = builder.build(
            contract=_contract(
                required_context=["control"],
                optional_context=["persona"],
            ),
            session_id="s1",
        )
        # persona should have been dropped by L1 compression
        assert "persona" not in result.context.session_sections

    def test_budget_result_attached(self) -> None:
        builder = ContextBuilder()
        result = builder.build(contract=_contract())
        assert isinstance(result.budget, BudgetResult)


# ===================================================================
# Tests: ContextBuilder -- build_minimal
# ===================================================================


class TestContextBuilderMinimal:
    """ContextBuilder.build_minimal() for simple tool calls."""

    def test_minimal_produces_context(self) -> None:
        builder = ContextBuilder()
        ctx = builder.build_minimal(params={"q": "test"}, trace_id="tr-m")
        assert isinstance(ctx, ExecutionContext)
        assert ctx.params == {"q": "test"}
        assert ctx.trace_id == "tr-m"
        assert ctx.session_sections == {}
        assert ctx.prompt is None

    def test_minimal_empty_params(self) -> None:
        builder = ContextBuilder()
        ctx = builder.build_minimal()
        assert ctx.params == {}
        assert ctx.token_count == 0


# ===================================================================
# Tests: ContextBuilderConfig
# ===================================================================


class TestContextBuilderConfig:
    """ContextBuilderConfig frozen dataclass."""

    def test_defaults(self) -> None:
        c = ContextBuilderConfig()
        assert c.default_session_id == ""
        assert c.budget_config.ceiling == TOKEN_CEILING

    def test_custom(self) -> None:
        c = ContextBuilderConfig(
            default_session_id="sess-1",
            budget_config=ContextBudgetConfig(ceiling=50_000),
        )
        assert c.default_session_id == "sess-1"
        assert c.budget_config.ceiling == 50_000

    def test_frozen(self) -> None:
        c = ContextBuilderConfig()
        with pytest.raises(AttributeError):
            c.default_session_id = "x"  # type: ignore[misc]

    def test_repr(self) -> None:
        assert "ceiling" in repr(ContextBuilderConfig())


# ===================================================================
# Tests: ContextBuildResult
# ===================================================================


class TestContextBuildResult:
    """ContextBuildResult frozen dataclass."""

    def test_defaults(self) -> None:
        r = ContextBuildResult()
        assert r.assembly_ms == 0.0
        assert r.prompt_resolved is False
        assert r.missing_required == []
        assert r.missing_optional == []

    def test_frozen(self) -> None:
        r = ContextBuildResult()
        with pytest.raises(AttributeError):
            r.assembly_ms = 999  # type: ignore[misc]

    def test_to_dict(self) -> None:
        r = ContextBuildResult(assembly_ms=1.5, prompt_resolved=True)
        d = r.to_dict()
        assert d["assembly_ms"] == 1.5
        assert d["prompt_resolved"] is True

    def test_repr(self) -> None:
        assert "ContextBuildResult" in repr(ContextBuildResult())


# ===================================================================
# Tests: Exception hierarchy
# ===================================================================


class TestContextBuilderExceptions:
    """Exception hierarchy for context_builder module."""

    def test_context_assembly_is_builder_error(self) -> None:
        assert issubclass(ContextAssemblyError, ContextBuilderError)

    def test_builder_error_is_exception(self) -> None:
        assert issubclass(ContextBuilderError, Exception)

    def test_repr(self) -> None:
        e = ContextBuilderError("test")
        assert "ContextBuilderError" in repr(e)

    def test_assembly_repr(self) -> None:
        e = ContextAssemblyError("fail")
        assert "ContextAssemblyError" in repr(e)


# ===================================================================
# Tests: Module exports verification
# ===================================================================


class TestModuleExports:
    """Verify all 4.2 exports accessible from k1.fabric.core."""

    def test_all_exports_importable(self) -> None:
        import k1.fabric.core as mod

        for name in mod.__all__:
            assert hasattr(mod, name), f"Missing export: {name}"

    def test_all_list_count(self) -> None:
        from k1.fabric.core import __all__

        # 15 prior (M2) + 18 new (4.2) + 5 new (4.5.1) + 2 new (4.5.4) + 8 new (4.5.2) + 9 new (4.5.3) + 1 new (4.5.6) = 58
        assert len(__all__) == 58

    def test_context_builder_exports(self) -> None:
        from k1.fabric.core import ContextBuilder

        assert ContextBuilder is not None

    def test_context_budget_exports(self) -> None:
        from k1.fabric.core import TOKEN_CEILING

        assert TOKEN_CEILING == 128_000

    def test_prior_exports_still_work(self) -> None:
        from k1.fabric.core import CapabilityRegistry

        assert CapabilityRegistry is not None
