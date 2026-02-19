"""Tests for Epic 3.1 Scratchpad Models: PAD-001.

Test classes:
    TestFinding                  -- Finding dataclass
    TestLoopBudget               -- LoopBudget tier presets, exhaustion, counters
    TestToolEntry                -- ToolEntry dataclass
    TestScratchpad               -- Scratchpad with findings, tool history, compaction
    TestScratchpadFSMState       -- fsm_state field on Scratchpad
    TestCognitiveTools           -- COGNITIVE_TOOLS frozenset (7 names)
    TestNeedsCompaction          -- token-based compaction threshold
"""

from __future__ import annotations

import pytest

from poc.concierge_fsm_poc.fsm.controller import State
from poc.concierge_fsm_poc.react.scratchpad import (
    COGNITIVE_TOOLS,
    Finding,
    LoopBudget,
    Scratchpad,
    Tier,
    ToolEntry,
)

# ===========================================================================
# TestCognitiveTools
# ===========================================================================


class TestCognitiveTools:
    """AC: COGNITIVE_TOOLS frozenset with all 7 cognitive/signal tool names."""

    def test_is_frozenset(self):
        assert isinstance(COGNITIVE_TOOLS, frozenset)

    def test_has_six_tools(self):
        assert len(COGNITIVE_TOOLS) == 6

    def test_update_beliefs_present(self):
        assert "update_beliefs" in COGNITIVE_TOOLS

    def test_update_scoreboard_present(self):
        assert "update_scoreboard" in COGNITIVE_TOOLS

    def test_update_clarifications_present(self):
        assert "update_clarifications" in COGNITIVE_TOOLS

    def test_update_narrative_present(self):
        assert "update_narrative" in COGNITIVE_TOOLS

    def test_refine_affect_present(self):
        assert "refine_affect" in COGNITIVE_TOOLS

    def test_promote_belief_present(self):
        assert "promote_belief" in COGNITIVE_TOOLS

    def test_non_cognitive_tool_absent(self):
        assert "invoke_capability" not in COGNITIVE_TOOLS
        assert "recall_memory" not in COGNITIVE_TOOLS

    def test_expected_names(self):
        expected = {
            "update_beliefs",
            "update_scoreboard",
            "update_clarifications",
            "update_narrative",
            "refine_affect",
            "promote_belief",
        }
        assert COGNITIVE_TOOLS == expected


# ===========================================================================
# TestFinding
# ===========================================================================


class TestFinding:
    """AC: Finding dataclass with key, value, type, confidence, source fields."""

    def test_basic_creation(self):
        f = Finding(key="temp", value=72)
        assert f.key == "temp"
        assert f.value == 72

    def test_default_type_is_fact(self):
        f = Finding(key="k", value="v")
        assert f.type == "fact"

    def test_custom_type(self):
        f = Finding(key="k", value="v", type="weather")
        assert f.type == "weather"

    def test_default_confidence(self):
        f = Finding(key="k", value="v")
        assert f.confidence == 1.0

    def test_partial_confidence(self):
        f = Finding(key="k", value="v", confidence=0.7)
        assert f.confidence == 0.7

    def test_source_iteration_default(self):
        f = Finding(key="k", value="v")
        assert f.source_iteration == 0

    def test_source_tool_default(self):
        f = Finding(key="k", value="v")
        assert f.source_tool == ""

    def test_source_tool_set(self):
        f = Finding(key="k", value="v", source_tool="weather_api")
        assert f.source_tool == "weather_api"


# ===========================================================================
# TestLoopBudget
# ===========================================================================


class TestLoopBudget:
    """AC: LoopBudget with tier presets, exhaustion, counters."""

    def test_default_values(self):
        b = LoopBudget()
        assert b.max_tools == 200
        assert b.max_iterations == 200
        assert b.max_context_tokens == 128_000

    # -- Tier presets -------------------------------------------------------

    def test_low_tier_preset(self):
        b = LoopBudget.for_tier(Tier.LOW)
        assert b.max_tools == 5
        assert b.max_iterations == 3
        assert b.timeout_ms == 45_000
        assert b.max_tokens_out == 16_000

    def test_medium_tier_preset(self):
        b = LoopBudget.for_tier(Tier.MEDIUM)
        assert b.max_tools == 15
        assert b.max_iterations == 6
        assert b.timeout_ms == 120_000
        assert b.max_tokens_out == 32_000

    def test_high_tier_preset(self):
        b = LoopBudget.for_tier(Tier.HIGH)
        assert b.max_tools == 30
        assert b.max_iterations == 10
        assert b.timeout_ms == 300_000
        assert b.max_tokens_out == 64_000

    # -- Exhaustion ---------------------------------------------------------

    def test_not_exhausted_initially(self):
        b = LoopBudget()
        assert b.exhausted is False

    def test_exhausted_by_tools(self):
        b = LoopBudget(max_tools=2)
        b.tools_used = 2
        assert b.exhausted is True

    def test_exhausted_by_iterations(self):
        b = LoopBudget(max_iterations=3)
        b.iterations_used = 3
        assert b.exhausted is True

    def test_exhausted_by_timeout(self):
        b = LoopBudget(timeout_ms=100)
        b.elapsed_ms = 100
        assert b.exhausted is True

    # -- Remaining ----------------------------------------------------------

    def test_remaining_tools(self):
        b = LoopBudget(max_tools=5)
        b.tools_used = 3
        assert b.remaining_tools == 2

    def test_remaining_tools_never_negative(self):
        b = LoopBudget(max_tools=2)
        b.tools_used = 10
        assert b.remaining_tools == 0

    def test_remaining_iterations(self):
        b = LoopBudget(max_iterations=8)
        b.iterations_used = 5
        assert b.remaining_iterations == 3

    # -- Consume / add tokens -----------------------------------------------

    def test_consume_tool(self):
        b = LoopBudget()
        b.consume_tool()
        assert b.tools_used == 1

    def test_consume_iteration(self):
        b = LoopBudget()
        b.consume_iteration()
        assert b.iterations_used == 1

    def test_add_tokens(self):
        b = LoopBudget()
        b.add_tokens(100, 50)
        assert b.tokens_in == 100
        assert b.tokens_out == 50
        b.add_tokens(200, 80)
        assert b.tokens_in == 300
        assert b.tokens_out == 130


# ===========================================================================
# TestToolEntry
# ===========================================================================


class TestToolEntry:
    """ToolEntry lightweight history row."""

    def test_basic_creation(self):
        e = ToolEntry(iteration=1, tool_name="recall_memory")
        assert e.iteration == 1
        assert e.tool_name == "recall_memory"
        assert e.ok is True
        assert e.summary == ""

    def test_failed_entry(self):
        e = ToolEntry(
            iteration=3, tool_name="invoke_capability", ok=False, summary="circuit breaker open"
        )
        assert e.ok is False
        assert "circuit breaker" in e.summary


# ===========================================================================
# TestScratchpad
# ===========================================================================


class TestScratchpad:
    """AC: Scratchpad with findings, tool history, budget, compaction."""

    @pytest.fixture()
    def pad(self):
        return Scratchpad(
            system_prompt="You are the concierge.",
            user_query="Plan a Lake Tahoe trip",
            tier=Tier.MEDIUM,
        )

    # -- Defaults -----------------------------------------------------------

    def test_default_iteration(self, pad):
        assert pad.iteration == 0

    def test_turn_id_generated(self, pad):
        assert pad.turn_id.startswith("turn-")
        assert len(pad.turn_id) > 8

    def test_default_tier(self):
        p = Scratchpad()
        assert p.tier == Tier.MEDIUM

    def test_empty_findings(self, pad):
        assert pad.findings == {}

    def test_empty_tool_history(self, pad):
        assert pad.tool_history == []

    def test_budget_created(self, pad):
        assert isinstance(pad.budget, LoopBudget)

    # -- Findings -----------------------------------------------------------

    def test_add_finding(self, pad):
        pad.add_finding(Finding(key="weather", value="sunny"))
        assert "weather" in pad.findings
        assert pad.findings["weather"].value == "sunny"

    def test_add_finding_sets_source_iteration(self, pad):
        pad.iteration = 3
        pad.add_finding(Finding(key="temp", value=72))
        assert pad.findings["temp"].source_iteration == 3

    def test_add_duplicate_finding_skipped(self, pad):
        pad.add_finding(Finding(key="city", value="Tahoe"))
        pad.add_finding(Finding(key="city", value="Tahoe"))
        assert len(pad.findings) == 1

    def test_add_collision_namespaced(self, pad):
        pad.add_finding(Finding(key="price", value=100))
        pad.add_finding(Finding(key="price", value=200))
        assert len(pad.findings) == 2
        assert "price" in pad.findings
        assert "price_2" in pad.findings

    def test_add_multiple_collisions(self, pad):
        for i in range(4):
            pad.add_finding(Finding(key="item", value=i))
        assert len(pad.findings) == 4
        assert "item" in pad.findings
        assert "item_2" in pad.findings
        assert "item_3" in pad.findings
        assert "item_4" in pad.findings

    def test_add_findings_batch(self, pad):
        pad.add_findings(
            [
                Finding(key="a", value=1),
                Finding(key="b", value=2),
                Finding(key="c", value=3),
            ]
        )
        assert len(pad.findings) == 3

    def test_findings_summary_empty(self, pad):
        assert pad.findings_summary() == ""

    def test_findings_summary_not_empty(self, pad):
        pad.add_finding(Finding(key="weather", value="sunny", type="weather"))
        summary = pad.findings_summary()
        assert "WEATHER" in summary
        assert "weather: sunny" in summary

    def test_findings_summary_groups_by_type(self, pad):
        pad.add_finding(Finding(key="temp", value=72, type="weather"))
        pad.add_finding(Finding(key="hotel", value="Marriott", type="booking"))
        summary = pad.findings_summary()
        assert "WEATHER" in summary
        assert "BOOKING" in summary

    def test_findings_summary_shows_confidence(self, pad):
        pad.add_finding(Finding(key="guess", value="maybe", confidence=0.6))
        summary = pad.findings_summary()
        assert "60%" in summary

    # -- Tool history -------------------------------------------------------

    def test_record_tool_call(self, pad):
        pad.record_tool_call("recall_memory", {"query": "tahoe hotels"})
        assert len(pad.tool_history) == 1
        assert pad.tool_history[0].tool_name == "recall_memory"

    def test_record_tool_call_consumes_budget(self, pad):
        pad.record_tool_call("recall_memory")
        assert pad.budget.tools_used == 1

    def test_record_tool_call_sets_iteration(self, pad):
        pad.iteration = 5
        pad.record_tool_call("invoke_capability", ok=False, summary="timeout")
        assert pad.tool_history[0].iteration == 5

    def test_record_multiple_tool_calls(self, pad):
        pad.record_tool_call("update_beliefs")
        pad.record_tool_call("update_scoreboard")
        pad.record_tool_call("invoke_capability")
        assert len(pad.tool_history) == 3
        assert pad.budget.tools_used == 3

    # -- is_complete --------------------------------------------------------

    def test_is_complete_false_initially(self, pad):
        assert pad.is_complete is False

    def test_is_complete_when_exhausted(self, pad):
        pad.budget = LoopBudget(max_tools=1)
        pad.budget.tools_used = 1
        assert pad.is_complete is True

    # -- elapsed_ms ---------------------------------------------------------

    def test_elapsed_ms_non_negative(self, pad):
        assert pad.elapsed_ms() >= 0

    # -- estimated_context_tokens -------------------------------------------

    def test_estimated_context_tokens_baseline(self, pad):
        tokens = pad.estimated_context_tokens()
        # system_prompt + user_query chars / 4
        expected_chars = len("You are the concierge.") + len("Plan a Lake Tahoe trip")
        assert tokens == expected_chars // 4

    def test_estimated_context_tokens_grows_with_findings(self, pad):
        before = pad.estimated_context_tokens()
        pad.add_finding(Finding(key="long_fact", value="x" * 400))
        after = pad.estimated_context_tokens()
        assert after > before


# ===========================================================================
# TestScratchpadFSMState
# ===========================================================================


class TestScratchpadFSMState:
    """AC: fsm_state field on Scratchpad."""

    def test_default_fsm_state(self):
        pad = Scratchpad()
        assert pad.fsm_state == State.LISTENING

    def test_fsm_state_set_on_creation(self):
        pad = Scratchpad(fsm_state=State.DISPATCHING)
        assert pad.fsm_state == State.DISPATCHING

    def test_fsm_state_mutable(self):
        pad = Scratchpad()
        pad.fsm_state = State.COMPANIONING
        assert pad.fsm_state == State.COMPANIONING

    @pytest.mark.parametrize("state", list(State))
    def test_fsm_state_accepts_all_states(self, state: State):
        pad = Scratchpad(fsm_state=state)
        assert pad.fsm_state == state


# ===========================================================================
# TestNeedsCompaction
# ===========================================================================


class TestNeedsCompaction:
    """AC: needs_compaction() works with token-based ratio (0.8 of 128K)."""

    def test_false_for_empty_scratchpad(self):
        pad = Scratchpad()
        assert pad.needs_compaction() is False

    def test_false_for_small_content(self):
        pad = Scratchpad(
            system_prompt="short prompt",
            user_query="short query",
        )
        assert pad.needs_compaction() is False

    def test_true_when_over_threshold(self):
        """Fill tool history summaries until over 80% of 128K tokens."""
        pad = Scratchpad()
        # 128K tokens * 0.8 = 102,400 tokens = ~409,600 chars
        # Each summary entry = 1000 chars = ~250 tokens
        # Need 410 entries to cross threshold
        for i in range(420):
            pad.tool_history.append(ToolEntry(iteration=i, tool_name="t", summary="x" * 1000))
        assert pad.needs_compaction() is True

    def test_custom_ratio(self):
        """Lower ratio triggers compaction sooner."""
        pad = Scratchpad(compaction_token_ratio=0.001)
        pad.tool_history.append(ToolEntry(iteration=0, tool_name="t", summary="x" * 100))
        # max_context_tokens=128000, 0.001 * 128000 = 128 tokens
        # 100 chars = 25 tokens -- still under
        assert pad.needs_compaction() is False

        pad.tool_history.append(ToolEntry(iteration=1, tool_name="t", summary="x" * 1000))
        # Now ~275 tokens > 128 threshold
        assert pad.needs_compaction() is True

    def test_compaction_summaries_counted(self):
        """Compaction summaries contribute to token estimate."""
        pad = Scratchpad(compaction_token_ratio=0.001)
        pad.add_compaction_summary("x" * 1000)
        assert pad.needs_compaction() is True

    def test_add_compaction_summary(self):
        pad = Scratchpad()
        assert pad.compaction_count == 0
        pad.add_compaction_summary("Summary of turns 1-5")
        assert pad.compaction_count == 1
        pad.add_compaction_summary("Summary of turns 6-10")
        assert pad.compaction_count == 2
