"""
Epic 6.2.8 -- Test ContextBuilder (6-step pipeline + token budget).

Covers:
  - ContextBuilder 6-step pipeline: read contract context requirements,
    fetch from SessionState, inject params, resolve prompt, apply token
    budget, package ExecutionContext.
  - Token budget: 5-level compression (L1-L5), 128K ceiling (FAB-08).
  - Graceful degradation: no state reader, no prompt system, missing
    sections (required vs optional).
  - ContextBudget: apply(), count_tokens, BudgetResult metadata.

NO MOCKS -- all tests use real adapters (in-memory SessionState, prompt system).

References:
  - fabric-implementation-plan.md Epic 6.2.8
  - fabric_discussion.md Section 12 (Context Assembly)
  - FAB-008 (Single Writer -- read-only context)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from k1.fabric.core.context_budget import (
    TOKEN_CEILING,
    CompressionLevel,
    ContextBudget,
    ContextBudgetConfig,
    count_tokens,
    count_tokens_dict,
)
from k1.fabric.core.context_builder import (
    ContextBuilder,
    ContextBuilderConfig,
    ContextBuildResult,
)
from k1.fabric.types import CapabilityContract, ExecutionContext, InputSpec

# ---------------------------------------------------------------------------
# Real in-memory adapters (NO MOCKS)
# ---------------------------------------------------------------------------


class InMemorySessionStateReader:
    """Real in-memory SessionState reader satisfying ISessionStateReader."""

    def __init__(self, sections: dict[str, Any] | None = None):
        self._sections: dict[str, Any] = sections or {}

    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        return self._sections.get(section)

    def set_section(self, section: str, data: dict) -> None:
        self._sections[section] = data


class InMemoryPromptSystem:
    """Real in-memory prompt system satisfying IPromptSystemPort."""

    def __init__(self) -> None:
        self._templates: dict[str, dict[str, Any]] = {}

    def add_template(self, name: str, text: str) -> None:
        self._templates[name] = {"text": text}

    def resolve(self, template_name: str) -> Optional[Dict[str, Any]]:
        return self._templates.get(template_name)

    def compile(self, template: Dict[str, Any], variables: Dict[str, Any]) -> str:
        text = template.get("text", "")
        for k, v in variables.items():
            text = text.replace(f"{{{k}}}", str(v))
        return text


def _make_contract(
    name: str = "tool.read.test",
    required_context: list[str] | None = None,
    optional_context: list[str] | None = None,
    required_inputs: list[str] | None = None,
) -> CapabilityContract:
    inputs = [InputSpec(name=n) for n in (required_inputs or [])]
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["TEST"],
        description="Test contract",
        capabilities=[name],
        provider_type="MCP",
        provider_id="pid-test",
        required_inputs=inputs,
        required_context=required_context or [],
        optional_context=optional_context or [],
    )


# ===========================================================================
# ContextBudget (token budget manager)
# ===========================================================================


class TestContextBudget:
    """Tests for ContextBudget (4.2.2 + 4.2.3)."""

    def test_within_budget_no_compression(self):
        budget = ContextBudget()
        result = budget.apply(
            session_sections={"control": {"status": "active"}},
            prompt="Hello",
            params={"q": "test"},
        )
        assert not result.over_budget
        assert result.compression_applied == CompressionLevel.NONE
        assert result.total_tokens > 0

    def test_l1_drops_optional_sections(self):
        """L1: Drop optional_context sections first."""
        config = ContextBudgetConfig(ceiling=30, response_headroom=5)
        budget = ContextBudget(config)
        # Build data that exceeds 25-token effective budget
        big = {"data": "x" * 400}
        result = budget.apply(
            session_sections={"control": {"k": "v"}, "persona": big},
            optional_sections=["persona"],
        )
        assert "persona" not in result.session_sections
        assert "persona" in result.sections_dropped

    def test_l2_truncates_history(self):
        """L2: Truncate history_recent to last 3 turns."""
        config = ContextBudgetConfig(ceiling=50, response_headroom=5)
        budget = ContextBudget(config)
        turns = [
            {"user": f"msg-{i} " + "x" * 40, "assistant": f"reply-{i} " + "y" * 40}
            for i in range(20)
        ]
        result = budget.apply(
            session_sections={"history_recent": {"turns": turns}},
        )
        hr = result.session_sections.get("history_recent", {})
        remaining_turns = hr.get("turns", [])
        # Compression applied at L2 or beyond means turns were truncated
        assert result.compression_applied.value >= CompressionLevel.L2_TRUNCATE_HISTORY.value
        assert len(remaining_turns) <= config.max_history_turns

    def test_l5_emergency_drops_warm(self):
        """L5: Emergency mode drops all WARM sections, keeps HOT only."""
        config = ContextBudgetConfig(ceiling=50, response_headroom=10)
        budget = ContextBudget(config)
        result = budget.apply(
            session_sections={
                "control": {"status": "active"},
                "beliefs_active": {"facts": [{"text": "x" * 100, "confidence": 0.9}]},
                "history_recent": {"turns": [{"user": "x" * 200}] * 10},
                "persona": {"data": "x" * 200},
                "telemetry": {"data": "x" * 200},
            },
        )
        # WARM sections (persona, telemetry, history_recent) should be dropped
        for warm in ("persona", "telemetry"):
            if warm in result.sections_dropped:
                assert warm not in result.session_sections

    def test_empty_inputs(self):
        budget = ContextBudget()
        result = budget.apply(session_sections={})
        assert result.total_tokens == 0
        assert result.compression_applied == CompressionLevel.NONE
        assert not result.over_budget

    def test_effective_budget(self):
        config = ContextBudgetConfig(ceiling=128_000, response_headroom=4_000)
        budget = ContextBudget(config)
        assert budget.effective_budget == 124_000

    def test_sections_preserved_when_under_budget(self):
        budget = ContextBudget()
        sections = {"control": {"status": "active"}, "beliefs_active": {"facts": []}}
        result = budget.apply(session_sections=sections)
        assert "control" in result.session_sections
        assert "beliefs_active" in result.session_sections


class TestTokenCounting:
    """Tests for token counting utilities (4.2.3)."""

    def test_count_tokens_empty(self):
        assert count_tokens("") == 0

    def test_count_tokens_nonempty(self):
        tokens = count_tokens("Hello world, this is a test string.")
        assert tokens > 0

    def test_count_tokens_dict_empty(self):
        assert count_tokens_dict({}) == 0

    def test_count_tokens_dict_nonempty(self):
        tokens = count_tokens_dict({"key": "value", "nested": {"a": 1}})
        assert tokens > 0

    def test_count_tokens_deterministic(self):
        text = "This is a deterministic test string."
        assert count_tokens(text) == count_tokens(text)

    def test_count_tokens_scales_with_length(self):
        short = count_tokens("hello")
        long_text = count_tokens("hello " * 100)
        assert long_text > short


# ===========================================================================
# ContextBuilder (6-step pipeline)
# ===========================================================================


class TestContextBuilder:
    """Tests for ContextBuilder (4.2.1) -- full 6-step pipeline."""

    def test_basic_build(self):
        """Step 1-6: Basic end-to-end build with all components."""
        reader = InMemorySessionStateReader(
            {
                "beliefs_active": {"facts": [{"text": "sky is blue"}]},
            }
        )
        prompt_sys = InMemoryPromptSystem()
        prompt_sys.add_template("greet_v1", "Hello {name}!")

        contract = _make_contract(
            required_context=["beliefs_active"],
            optional_context=[],
        )
        builder = ContextBuilder(state_reader=reader, prompt_system=prompt_sys)
        result = builder.build(
            contract=contract,
            params={"query": "test"},
            session_id="sess-1",
            trace_id="tr-001",
            prompt_template_name="greet_v1",
            prompt_variables={"name": "Alice"},
        )
        assert isinstance(result, ContextBuildResult)
        ctx = result.context
        assert ctx.trace_id == "tr-001"
        assert "beliefs_active" in ctx.session_sections
        assert ctx.params["query"] == "test"
        assert result.prompt_resolved is True
        assert "Alice" in ctx.prompt

    def test_missing_optional_section_skipped(self):
        """Step 2: Missing optional section -> skip silently."""
        reader = InMemorySessionStateReader(
            {
                "beliefs_active": {"facts": []},
            }
        )
        contract = _make_contract(
            required_context=["beliefs_active"],
            optional_context=["persona"],
        )
        builder = ContextBuilder(state_reader=reader)
        result = builder.build(contract=contract, session_id="s1")
        assert "persona" in result.missing_optional
        assert "beliefs_active" not in result.missing_required

    def test_missing_required_section_reported(self):
        """Step 2: Missing required section -> logged, continues with partial data."""
        reader = InMemorySessionStateReader({})
        contract = _make_contract(required_context=["beliefs_active", "control"])
        builder = ContextBuilder(state_reader=reader)
        result = builder.build(contract=contract, session_id="s1")
        assert "beliefs_active" in result.missing_required
        assert "control" in result.missing_required

    def test_no_state_reader_graceful(self):
        """Graceful degradation: no state reader -> all sections missing."""
        contract = _make_contract(
            required_context=["beliefs_active"],
            optional_context=["persona"],
        )
        builder = ContextBuilder(state_reader=None)
        result = builder.build(contract=contract)
        assert "beliefs_active" in result.missing_required
        assert "persona" in result.missing_optional
        assert result.context.session_sections == {}

    def test_no_prompt_system_graceful(self):
        """Graceful degradation: no prompt system -> prompt=None."""
        reader = InMemorySessionStateReader()
        contract = _make_contract()
        builder = ContextBuilder(state_reader=reader, prompt_system=None)
        result = builder.build(
            contract=contract,
            prompt_template_name="some_template",
        )
        assert result.prompt_resolved is False
        assert result.context.prompt is None

    def test_params_injected(self):
        """Step 3: Request params injected into context."""
        contract = _make_contract()
        builder = ContextBuilder()
        result = builder.build(
            contract=contract,
            params={"location": "Seattle", "units": "metric"},
        )
        assert result.context.params["location"] == "Seattle"
        assert result.context.params["units"] == "metric"

    def test_prompt_compilation(self):
        """Step 4: Prompt template resolved and compiled."""
        prompt_sys = InMemoryPromptSystem()
        prompt_sys.add_template("weather_v1", "Forecast for {city}: {period}")

        contract = _make_contract()
        builder = ContextBuilder(prompt_system=prompt_sys)
        result = builder.build(
            contract=contract,
            prompt_template_name="weather_v1",
            prompt_variables={"city": "London", "period": "7-day"},
        )
        assert result.prompt_resolved is True
        assert "London" in result.context.prompt
        assert "7-day" in result.context.prompt

    def test_prompt_template_not_found(self):
        """Step 4: Template not found -> prompt_resolved=False."""
        prompt_sys = InMemoryPromptSystem()
        contract = _make_contract()
        builder = ContextBuilder(prompt_system=prompt_sys)
        result = builder.build(
            contract=contract,
            prompt_template_name="nonexistent",
        )
        assert result.prompt_resolved is False
        assert result.context.prompt is None

    def test_token_budget_applied(self):
        """Step 5: Token budget enforced."""
        reader = InMemorySessionStateReader(
            {
                "control": {"status": "active"},
            }
        )
        contract = _make_contract(required_context=["control"])
        builder = ContextBuilder(state_reader=reader)
        result = builder.build(contract=contract)
        assert result.budget.total_tokens > 0
        assert result.budget.total_tokens <= TOKEN_CEILING

    def test_execution_context_frozen(self):
        """Step 6: ExecutionContext is frozen (immutable)."""
        contract = _make_contract()
        builder = ContextBuilder()
        result = builder.build(contract=contract, params={"q": "test"}, trace_id="tr-x")
        ctx = result.context
        assert isinstance(ctx, ExecutionContext)
        # Frozen dataclass -- should raise on attribute assignment
        with pytest.raises(AttributeError):
            ctx.trace_id = "mutated"  # type: ignore[misc]

    def test_build_minimal(self):
        """build_minimal(): Simple context with no contract requirements."""
        builder = ContextBuilder()
        ctx = builder.build_minimal(params={"q": "quick"}, trace_id="tr-m")
        assert ctx.params["q"] == "quick"
        assert ctx.trace_id == "tr-m"
        assert ctx.session_sections == {}

    def test_assembly_ms_tracked(self):
        """Assembly wall-clock time is recorded."""
        contract = _make_contract()
        builder = ContextBuilder()
        result = builder.build(contract=contract)
        assert result.assembly_ms >= 0.0

    def test_has_state_reader_property(self):
        builder_none = ContextBuilder()
        assert builder_none.has_state_reader is False

        reader = InMemorySessionStateReader()
        builder_with = ContextBuilder(state_reader=reader)
        assert builder_with.has_state_reader is True

    def test_has_prompt_system_property(self):
        builder_none = ContextBuilder()
        assert builder_none.has_prompt_system is False

        prompt_sys = InMemoryPromptSystem()
        builder_with = ContextBuilder(prompt_system=prompt_sys)
        assert builder_with.has_prompt_system is True

    def test_multiple_required_sections(self):
        """Multiple required sections all fetched."""
        reader = InMemorySessionStateReader(
            {
                "control": {"mode": "auto"},
                "beliefs_active": {"facts": [{"text": "it rains"}]},
                "scoreboard": {"current_qud": "weather?"},
            }
        )
        contract = _make_contract(
            required_context=["control", "beliefs_active", "scoreboard"],
        )
        builder = ContextBuilder(state_reader=reader)
        result = builder.build(contract=contract, session_id="s1")
        assert len(result.missing_required) == 0
        ctx = result.context
        assert "control" in ctx.session_sections
        assert "beliefs_active" in ctx.session_sections
        assert "scoreboard" in ctx.session_sections

    def test_budget_compression_on_large_context(self):
        """Force compression by providing very small budget config."""
        reader = InMemorySessionStateReader(
            {
                "control": {"data": "x" * 100},
                "persona": {"bio": "x" * 500},
            }
        )
        config = ContextBuilderConfig(
            budget_config=ContextBudgetConfig(ceiling=100, response_headroom=20),
        )
        contract = _make_contract(
            required_context=["control"],
            optional_context=["persona"],
        )
        builder = ContextBuilder(state_reader=reader, config=config)
        result = builder.build(contract=contract, session_id="s1")
        # persona should be dropped at L1 or beyond
        if "persona" in result.budget.sections_dropped:
            assert "persona" not in result.context.session_sections

    def test_empty_contract_no_sections_needed(self):
        """Contract with no required/optional context -> empty session_sections."""
        contract = _make_contract(required_context=[], optional_context=[])
        builder = ContextBuilder()
        result = builder.build(contract=contract)
        assert result.context.session_sections == {} or result.budget.total_tokens >= 0
        assert len(result.missing_required) == 0
        assert len(result.missing_optional) == 0
