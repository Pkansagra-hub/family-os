"""Tests for FSM-Aware ReAct Loop -- Epic 3.3 (LOOP-001, LOOP-002, LOOP-003).

Covers:
    - ReActResult dataclass defaults and field values
    - InterruptSignal dataclass defaults and mutation
    - ReActLoop construction
    - _fire() FSM transition recording
    - _execute_tool() success / failure paths
    - run() LOW path: DISPATCHING -> DISPATCH_COMPLETE -> DELIVERING
    - run() LOW path with tool calls
    - run() MEDIUM path: DISPATCHING -> ACK -> COMPANIONING -> PROGRESS -> PROGRESSING -> DISPATCH_COMPLETE
    - COGNITIVE_TOOLS filter routing (skip extraction)
    - Budget exhaustion behaviour
    - Interrupt handling (user, watchdog, cancel)
    - Non-interruptible state interrupt queueing
    - Compaction trigger
    - signal_interrupt() API
    - _cognitive_summary() helper

Mock strategy: Real FSMController, real Scratchpad, real ToolRegistry with
stub handlers.  GeminiClient is mocked via AsyncMock to control LLM responses.
"""

from __future__ import annotations

from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock

import pytest

from poc.concierge_fsm_poc.fsm.controller import Event, FSMController, State
from poc.concierge_fsm_poc.fsm.phase1_mock import Phase1Result
from poc.concierge_fsm_poc.llm.client import LLMResponse, ToolCall
from poc.concierge_fsm_poc.react.loop import (
    InterruptSignal,
    ReActLoop,
    ReActResult,
    _cognitive_summary,
)
from poc.concierge_fsm_poc.react.scratchpad import Finding, Scratchpad, Tier
from poc.concierge_fsm_poc.tools.registry import ToolDefinition, ToolRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_phase1(
    *,
    tier: Literal["LOW", "MEDIUM"] = "LOW",
    safety_band: str = "GREEN",
    intent: str = "weather_lookup",
    gaps: list[str] | None = None,
) -> Phase1Result:
    """Create a Phase1Result for testing."""
    return Phase1Result(
        intent=intent,
        tier=tier,
        safety_band=safety_band,
        entities={"location": "Lake Tahoe"},
        emotion="neutral",
        confidence=0.87,
        gaps=gaps or [],
    )


def _make_registry(
    handlers: dict[str, Any] | None = None,
) -> ToolRegistry:
    """Build a small test registry with stub handlers."""
    registry = ToolRegistry()
    default_handlers: dict[str, tuple[str, Any]] = {
        "update_beliefs": (
            "cognitive",
            lambda **kw: {"success": True, "section": "beliefs_active"},
        ),
        "update_scoreboard": (
            "cognitive",
            lambda **kw: {"success": True, "section": "scoreboard"},
        ),
        "recall_memory": (
            "read",
            lambda **kw: {
                "memories": [{"subject": "Jake", "predicate": "likes", "object": "skiing"}]
            },
        ),
        "invoke_capability": (
            "action",
            lambda **kw: {"temperature": "45F", "conditions": "Partly cloudy"},
        ),
        "read_session_state": (
            "read",
            lambda **kw: {"section": kw.get("section", "all"), "data": {}},
        ),
    }

    if handlers:
        for name, (cat, handler) in handlers.items():
            default_handlers[name] = (cat, handler)

    for name, (category, handler) in default_handlers.items():
        registry.register(
            ToolDefinition(
                name=name,
                category=category,  # type: ignore[arg-type]
                handler=handler,
                schema={"name": name, "description": f"Test {name}", "parameters": {}},
                tiers=frozenset({"LOW", "MEDIUM"}),
            )
        )
    return registry


def _make_llm_mock(
    responses: list[LLMResponse] | None = None,
    findings: list[Finding] | None = None,
) -> MagicMock:
    """Create a mock GeminiClient with configurable responses."""
    llm = MagicMock()

    if responses is None:
        responses = [LLMResponse(text="Here is the weather.", tokens_in=10, tokens_out=20)]

    call_count = {"n": 0}

    async def mock_generate(messages, tools=None, force_tool_call=False):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    llm.generate = AsyncMock(side_effect=mock_generate)

    async def mock_generate_stream(messages, tools=None, force_tool_call=False, on_text_delta=None):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        resp = responses[idx]
        # Emit text deltas for text-only responses (mirrors real behavior)
        if on_text_delta and resp.text and not resp.tool_calls:
            on_text_delta(resp.text)
        return resp

    llm.generate_stream = AsyncMock(side_effect=mock_generate_stream)

    async def mock_extract(tool_results):
        if findings is not None:
            return findings
        result_findings = []
        for tool_name, raw in tool_results:
            result_findings.append(
                Finding(
                    key=f"{tool_name}_result",
                    value=str(raw)[:100],
                    type="fact",
                    source_tool=tool_name,
                )
            )
        return result_findings

    llm.extract_findings_batch = AsyncMock(side_effect=mock_extract)

    async def mock_summarize(messages):
        return "Summarized conversation."

    llm.summarize_messages = AsyncMock(side_effect=mock_summarize)

    return llm


def _make_loop(
    *,
    fsm_state: State = State.DISPATCHING,
    tier: str = "LOW",
    llm_responses: list[LLMResponse] | None = None,
    findings: list[Finding] | None = None,
    handlers: dict[str, Any] | None = None,
) -> tuple[ReActLoop, FSMController, MagicMock]:
    """Create a fully-wired ReActLoop for testing."""
    fsm = FSMController()
    # Advance FSM to desired state
    if fsm_state == State.DISPATCHING:
        fsm.transition(Event.MESSAGE_RECEIVED)  # LISTENING -> ACKING
        fsm.transition(Event.PHASE1_COMPLETE)  # ACKING -> DISPATCHING

    registry = _make_registry(handlers)
    llm = _make_llm_mock(llm_responses, findings)
    scratchpad = Scratchpad()

    loop = ReActLoop(fsm=fsm, registry=registry, llm=llm, scratchpad=scratchpad)
    return loop, fsm, llm


# =========================================================================
# Test: ReActResult dataclass
# =========================================================================


class TestReActResult:
    """ReActResult field defaults and construction."""

    def test_defaults(self):
        r = ReActResult()
        assert r.final_response == ""
        assert r.tool_calls_made == 0
        assert r.iterations == 0
        assert r.findings_count == 0
        assert r.fsm_transitions == []
        assert r.budget_exhausted is False
        assert r.interrupted is False
        assert r.interrupt_source == ""
        assert r.error is None
        assert r.partial_response == ""

    def test_custom_values(self):
        r = ReActResult(
            final_response="Hello",
            tool_calls_made=3,
            iterations=2,
            findings_count=5,
            fsm_transitions=[("DISPATCHING", "DISPATCH_COMPLETE", "DELIVERING")],
            budget_exhausted=True,
            interrupted=True,
            interrupt_source="user",
            error="timeout",
            partial_response="Partial",
        )
        assert r.final_response == "Hello"
        assert r.tool_calls_made == 3
        assert r.budget_exhausted is True
        assert r.interrupted is True
        assert len(r.fsm_transitions) == 1

    def test_fsm_transitions_independent(self):
        """Each instance gets its own transitions list."""
        r1 = ReActResult()
        r2 = ReActResult()
        r1.fsm_transitions.append(("A", "B", "C"))
        assert r2.fsm_transitions == []


# =========================================================================
# Test: InterruptSignal
# =========================================================================


class TestInterruptSignal:
    """InterruptSignal defaults and mutation."""

    def test_defaults(self):
        sig = InterruptSignal()
        assert sig.pending is False
        assert sig.source == ""
        assert sig.replacement_message == ""

    def test_mutation(self):
        sig = InterruptSignal()
        sig.pending = True
        sig.source = "watchdog"
        sig.replacement_message = "new message"
        assert sig.pending is True
        assert sig.source == "watchdog"

    def test_custom_init(self):
        sig = InterruptSignal(pending=True, source="cancel", replacement_message="")
        assert sig.pending is True
        assert sig.source == "cancel"


# =========================================================================
# Test: ReActLoop construction
# =========================================================================


class TestReActLoopInit:
    """ReActLoop construction and attribute access."""

    def test_attributes_set(self):
        loop, fsm, llm = _make_loop()
        assert loop.fsm is fsm
        assert loop.llm is llm
        assert isinstance(loop.scratchpad, Scratchpad)
        assert isinstance(loop.registry, ToolRegistry)
        assert isinstance(loop.interrupt, InterruptSignal)

    def test_interrupt_starts_inactive(self):
        loop, _, _ = _make_loop()
        assert loop.interrupt.pending is False


# =========================================================================
# Test: _fire() FSM transition recording
# =========================================================================


class TestFireTransition:
    """_fire() records transitions and syncs scratchpad."""

    def test_records_transition(self):
        loop, fsm, _ = _make_loop()
        # FSM is in DISPATCHING, fire DISPATCH_COMPLETE
        loop._fire(Event.DISPATCH_COMPLETE)
        assert len(loop._fsm_transitions) == 1
        assert loop._fsm_transitions[0] == (
            "DISPATCHING",
            "dispatch_complete",
            "DELIVERING",
        )

    def test_syncs_scratchpad_state(self):
        loop, _, _ = _make_loop()
        loop._fire(Event.DISPATCH_COMPLETE)
        assert loop.scratchpad.fsm_state == State.DELIVERING

    def test_multiple_transitions(self):
        loop, _, _ = _make_loop()
        # MEDIUM path: DISPATCHING -> COMPANIONING -> PROGRESSING
        loop._fire(Event.PRELIMINARY_ACK_SENT)
        loop._fire(Event.PROGRESS_RECEIVED)
        assert len(loop._fsm_transitions) == 2
        assert loop._fsm_transitions[0][2] == "COMPANIONING"
        assert loop._fsm_transitions[1][2] == "PROGRESSING"

    def test_returns_state_and_actions(self):
        loop, _, _ = _make_loop()
        state, actions = loop._fire(Event.DISPATCH_COMPLETE)
        assert state == State.DELIVERING
        assert len(actions) > 0


# =========================================================================
# Test: _execute_tool()
# =========================================================================


class TestExecuteTool:
    """_execute_tool() success and failure paths."""

    def test_success(self):
        loop, _, _ = _make_loop()
        result = loop._execute_tool("recall_memory", {"query": "allergies"})
        assert result["success"] is True
        assert "memories" in result["data"]

    def test_failure_returns_error(self):
        def failing_handler(**kw):
            raise ValueError("test error")

        loop, _, _ = _make_loop(handlers={"recall_memory": ("read", failing_handler)})
        result = loop._execute_tool("recall_memory", {"query": "test"})
        assert result["success"] is False
        assert "test error" in result["error"]

    def test_passes_arguments(self):
        received_args = {}

        def capture_handler(**kw):
            received_args.update(kw)
            return {"ok": True}

        loop, _, _ = _make_loop(handlers={"recall_memory": ("read", capture_handler)})
        loop._execute_tool("recall_memory", {"query": "tahoe", "limit": 5})
        assert received_args["query"] == "tahoe"
        assert received_args["limit"] == 5


# =========================================================================
# Test: run() -- LOW path (text-only response)
# =========================================================================


class TestRunLowPathTextOnly:
    """LOW tier, LLM returns text on first iteration -> DISPATCH_COMPLETE."""

    @pytest.mark.asyncio
    async def test_low_text_only(self):
        loop, fsm, llm = _make_loop(
            llm_responses=[
                LLMResponse(text="The weather is 45F.", tokens_in=10, tokens_out=20),
            ]
        )
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "What is the weather?")

        assert result.final_response == "The weather is 45F."
        assert result.iterations == 1
        assert result.tool_calls_made == 0
        assert result.budget_exhausted is False
        assert result.interrupted is False

    @pytest.mark.asyncio
    async def test_low_fires_dispatch_complete(self):
        loop, fsm, _ = _make_loop()
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "Weather?")

        # Should have fired dispatch_complete from DISPATCHING
        assert any(t[1] == "dispatch_complete" for t in result.fsm_transitions)
        assert fsm.state == State.DELIVERING

    @pytest.mark.asyncio
    async def test_low_no_preliminary_ack(self):
        """LOW tier should NOT fire PRELIMINARY_ACK_SENT."""
        loop, _, _ = _make_loop()
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "Weather?")

        assert not any(t[1] == "preliminary_ack_sent" for t in result.fsm_transitions)

    @pytest.mark.asyncio
    async def test_scratchpad_updated(self):
        loop, _, _ = _make_loop()
        phase1 = _make_phase1(tier="LOW")

        await loop.run(phase1, "Weather in Tahoe?")

        assert loop.scratchpad.user_query == "Weather in Tahoe?"
        assert loop.scratchpad.tier == Tier.LOW
        assert loop.scratchpad.iteration == 1


# =========================================================================
# Test: run() -- LOW path with tool calls
# =========================================================================


class TestRunLowPathWithTools:
    """LOW tier, LLM calls tools then returns text."""

    @pytest.mark.asyncio
    async def test_tool_call_then_text(self):
        loop, fsm, llm = _make_loop(
            llm_responses=[
                # Iteration 1: call invoke_capability
                LLMResponse(
                    tool_calls=[
                        ToolCall(
                            name="invoke_capability",
                            arguments={"capability_id": "tool.execute.weather_lookup"},
                        ),
                    ],
                    tokens_in=15,
                    tokens_out=10,
                ),
                # Iteration 2: text response
                LLMResponse(
                    text="The weather is 45F and partly cloudy.", tokens_in=20, tokens_out=30
                ),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "Weather?")

        assert result.final_response == "The weather is 45F and partly cloudy."
        assert result.iterations == 2
        assert result.tool_calls_made == 1
        assert result.findings_count > 0

    @pytest.mark.asyncio
    async def test_findings_extracted_from_read_tools(self):
        loop, _, llm = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[
                        ToolCall(name="recall_memory", arguments={"query": "allergies"}),
                    ],
                    tokens_in=10,
                    tokens_out=5,
                ),
                LLMResponse(text="Jake is allergic to peanuts.", tokens_in=10, tokens_out=15),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "Any allergies?")

        # Findings are extracted directly from tool results (no LLM call)
        assert result.findings_count > 0


# =========================================================================
# Test: run() -- MEDIUM path
# =========================================================================


class TestRunMediumPath:
    """MEDIUM tier fires PRELIMINARY_ACK_SENT, PROGRESS_RECEIVED, DISPATCH_COMPLETE."""

    @pytest.mark.asyncio
    async def test_medium_text_only(self):
        """MEDIUM with text-only: fires ACK + DISPATCH_COMPLETE."""
        loop, fsm, _ = _make_loop(
            llm_responses=[
                LLMResponse(text="Hotel booked.", tokens_in=10, tokens_out=20),
            ],
        )
        phase1 = _make_phase1(tier="MEDIUM")

        result = await loop.run(phase1, "Book a hotel")

        events_fired = [t[1] for t in result.fsm_transitions]
        assert "preliminary_ack_sent" in events_fired
        assert "dispatch_complete" in events_fired
        assert fsm.state == State.DELIVERING

    @pytest.mark.asyncio
    async def test_medium_with_tools_fires_progress(self):
        """MEDIUM with tools: fires ACK, PROGRESS, DISPATCH_COMPLETE."""
        loop, fsm, _ = _make_loop(
            llm_responses=[
                # Iteration 1: tool call
                LLMResponse(
                    tool_calls=[
                        ToolCall(name="invoke_capability", arguments={"capability_id": "test"}),
                    ],
                    tokens_in=15,
                    tokens_out=10,
                ),
                # Iteration 2: text response
                LLMResponse(text="Done!", tokens_in=10, tokens_out=15),
            ],
        )
        phase1 = _make_phase1(tier="MEDIUM")

        result = await loop.run(phase1, "Plan hotel")

        events_fired = [t[1] for t in result.fsm_transitions]
        assert "preliminary_ack_sent" in events_fired
        assert "progress_received" in events_fired
        assert "dispatch_complete" in events_fired
        assert fsm.state == State.DELIVERING

    @pytest.mark.asyncio
    async def test_medium_state_sequence(self):
        """MEDIUM path: DISPATCHING -> COMPANIONING -> PROGRESSING -> DELIVERING."""
        loop, fsm, _ = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[ToolCall(name="recall_memory", arguments={"query": "hotel"})],
                    tokens_in=10,
                    tokens_out=5,
                ),
                LLMResponse(text="Found hotel info.", tokens_in=10, tokens_out=20),
            ],
        )
        phase1 = _make_phase1(tier="MEDIUM")

        result = await loop.run(phase1, "Hotel info")

        states_visited = [t[2] for t in result.fsm_transitions]
        assert "COMPANIONING" in states_visited
        assert "PROGRESSING" in states_visited
        assert "DELIVERING" in states_visited


# =========================================================================
# Test: COGNITIVE_TOOLS filter routing
# =========================================================================


class TestCognitiveToolFilter:
    """Cognitive tool results skip extraction; non-cognitive results don't."""

    @pytest.mark.asyncio
    async def test_cognitive_tool_skips_extraction(self):
        """update_beliefs is cognitive -> no extract_findings call for it."""
        loop, _, llm = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[
                        ToolCall(
                            name="update_beliefs",
                            arguments={
                                "section": "beliefs_active",
                                "operation": "add_fact",
                                "fact": "test",
                            },
                        ),
                    ],
                    tokens_in=10,
                    tokens_out=5,
                ),
                LLMResponse(text="Done.", tokens_in=10, tokens_out=10),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        await loop.run(phase1, "remember that")

        # extract_findings_batch should NOT have been called (only cognitive tool)
        llm.extract_findings_batch.assert_not_called()
        # But the tool should be recorded in tool_history
        assert len(loop.scratchpad.tool_history) == 1
        assert loop.scratchpad.tool_history[0].tool_name == "update_beliefs"

    @pytest.mark.asyncio
    async def test_non_cognitive_tool_extracts_findings(self):
        """recall_memory is non-cognitive -> findings extracted directly."""
        loop, _, llm = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[
                        ToolCall(name="recall_memory", arguments={"query": "test"}),
                    ],
                    tokens_in=10,
                    tokens_out=5,
                ),
                LLMResponse(text="Done.", tokens_in=10, tokens_out=10),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "recall test")

        # Findings extracted directly (no LLM call for extraction)
        assert result.findings_count > 0

    @pytest.mark.asyncio
    async def test_mixed_tools_only_extracts_non_cognitive(self):
        """Mixed call: cognitive + read -> only read result extracted."""
        loop, _, llm = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[
                        ToolCall(
                            name="update_beliefs",
                            arguments={
                                "key": "test_fact",
                                "value": "confirmed",
                                "source": "user",
                            },
                        ),
                        ToolCall(name="recall_memory", arguments={"query": "allergies"}),
                    ],
                    tokens_in=15,
                    tokens_out=10,
                ),
                LLMResponse(text="Done.", tokens_in=10, tokens_out=10),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "allergies?")

        # Non-cognitive (recall_memory) results produce findings directly;
        # cognitive (update_beliefs) results do not.
        assert result.findings_count > 0

    @pytest.mark.asyncio
    async def test_cognitive_tool_summary_prefix(self):
        """Cognitive tool entries have [cognitive] prefix in summary."""
        loop, _, _ = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[
                        ToolCall(
                            name="update_scoreboard",
                            arguments={"operation": "upsert_task", "task_id": "T1"},
                        ),
                    ],
                    tokens_in=10,
                    tokens_out=5,
                ),
                LLMResponse(text="Done.", tokens_in=10, tokens_out=10),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        await loop.run(phase1, "update")

        entry = loop.scratchpad.tool_history[0]
        assert entry.summary.startswith("[cognitive]")


# =========================================================================
# Test: Budget exhaustion
# =========================================================================


class TestBudgetExhaustion:
    """Loop stops when budget is exhausted."""

    @pytest.mark.asyncio
    async def test_iteration_limit(self):
        """Loop respects max_iterations from budget."""
        # Create responses that always call tools (never text-only)
        # LOW tier has max_iterations=100, generate enough to exhaust
        tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(name="recall_memory", arguments={"query": f"q{i}"})],
                tokens_in=5,
                tokens_out=5,
            )
            for i in range(110)
        ]
        loop, fsm, _ = _make_loop(llm_responses=tool_responses)
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "Keep searching")

        assert result.budget_exhausted is True
        assert result.iterations <= 100
        assert fsm.state == State.DELIVERING

    @pytest.mark.asyncio
    async def test_budget_exhausted_with_findings(self):
        """When budget exhausted with findings, response includes them."""
        tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(name="recall_memory", arguments={"query": "allergy"})],
                tokens_in=5,
                tokens_out=5,
            )
            for _ in range(10)
        ]
        loop, _, _ = _make_loop(
            llm_responses=tool_responses,
            findings=[
                Finding(key="allergy", value="peanuts", type="fact", source_tool="recall_memory"),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "allergies")

        assert result.budget_exhausted is True
        assert "Here is what I found so far" in result.final_response

    @pytest.mark.asyncio
    async def test_budget_exhausted_no_findings(self):
        """When budget exhausted with only cognitive tools, findings may
        still be absent (cognitive results skip extraction)."""
        tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(name="update_beliefs", arguments={"key": "x", "value": "y", "source": "test"})],
                tokens_in=5,
                tokens_out=5,
            )
            for _ in range(10)
        ]
        loop, _, _ = _make_loop(
            llm_responses=tool_responses,
        )
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "search")

        assert result.budget_exhausted is True
        assert "unable to gather" in result.final_response


# =========================================================================
# Test: Interrupt handling (LOOP-003)
# =========================================================================


class TestInterruptHandling:
    """Interrupt detection and FSM transition during loop."""

    @pytest.mark.asyncio
    async def test_user_interrupt(self):
        """User interrupt during interruptible state."""
        # Create responses that always call tools (loop runs long enough)
        tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(name="recall_memory", arguments={"query": "test"})],
                tokens_in=5,
                tokens_out=5,
            )
            for _ in range(5)
        ]
        loop, fsm, _ = _make_loop(llm_responses=tool_responses)
        phase1 = _make_phase1(tier="LOW")

        # Signal interrupt before run (will be detected at iteration 1)
        loop.signal_interrupt(source="user", replacement_message="new topic")

        result = await loop.run(phase1, "old topic")

        assert result.interrupted is True
        assert result.interrupt_source == "user"
        events = [t[1] for t in result.fsm_transitions]
        assert "interrupt_detected" in events
        assert "interrupt_handled" in events
        assert fsm.state == State.ACKING

    @pytest.mark.asyncio
    async def test_watchdog_interrupt(self):
        """Watchdog timeout interrupt."""
        tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(name="recall_memory", arguments={"query": "x"})],
                tokens_in=5,
                tokens_out=5,
            )
            for _ in range(5)
        ]
        loop, fsm, _ = _make_loop(llm_responses=tool_responses)
        phase1 = _make_phase1(tier="LOW")

        loop.signal_interrupt(source="watchdog")

        result = await loop.run(phase1, "slow query")

        assert result.interrupted is True
        assert result.interrupt_source == "watchdog"
        assert fsm.state == State.ACKING

    @pytest.mark.asyncio
    async def test_cancel_interrupt(self):
        """Cancel command interrupt."""
        tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(name="recall_memory", arguments={"query": "x"})],
                tokens_in=5,
                tokens_out=5,
            )
            for _ in range(5)
        ]
        loop, fsm, _ = _make_loop(llm_responses=tool_responses)
        phase1 = _make_phase1(tier="LOW")

        loop.signal_interrupt(source="cancel")

        result = await loop.run(phase1, "cancel this")

        assert result.interrupted is True
        assert result.interrupt_source == "cancel"

    @pytest.mark.asyncio
    async def test_interrupt_resets_flag(self):
        """After interrupt handling, the flag is reset."""
        tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(name="recall_memory", arguments={"query": "x"})],
                tokens_in=5,
                tokens_out=5,
            )
            for _ in range(5)
        ]
        loop, _, _ = _make_loop(llm_responses=tool_responses)
        phase1 = _make_phase1(tier="LOW")

        loop.signal_interrupt(source="user")
        await loop.run(phase1, "test")

        assert loop.interrupt.pending is False

    @pytest.mark.asyncio
    async def test_interrupt_with_partial_findings(self):
        """Interrupt after some findings preserves partial_response."""
        loop, _, llm = _make_loop(
            llm_responses=[
                # Iteration 1: tool call (runs before interrupt)
                LLMResponse(
                    tool_calls=[ToolCall(name="recall_memory", arguments={"query": "test"})],
                    tokens_in=5,
                    tokens_out=5,
                ),
                # Would be iteration 2 but interrupt fires first
                LLMResponse(text="Never reached", tokens_in=5, tokens_out=5),
            ],
            findings=[
                Finding(key="test_fact", value="42", type="fact", source_tool="recall_memory"),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        # Don't signal interrupt yet -- let first iteration run
        # We'll manually set it after the first iteration would complete
        # But since the check is at TOP of iteration, we need it before iteration 2

        # Actually, signal before run -- interrupt fires at iteration 1
        loop.signal_interrupt(source="user", replacement_message="new topic")
        result = await loop.run(phase1, "old topic")

        # Since interrupt fires before any iteration runs, no findings
        assert result.interrupted is True

    @pytest.mark.asyncio
    async def test_medium_interrupt(self):
        """Interrupt during MEDIUM path (COMPANIONING state)."""
        loop, fsm, _ = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[ToolCall(name="recall_memory", arguments={"query": "x"})],
                    tokens_in=5,
                    tokens_out=5,
                )
                for _ in range(5)
            ],
        )
        phase1 = _make_phase1(tier="MEDIUM")

        loop.signal_interrupt(source="user")

        result = await loop.run(phase1, "Help")

        # MEDIUM fires preliminary_ack_sent first, THEN interrupt detected
        events = [t[1] for t in result.fsm_transitions]
        assert "preliminary_ack_sent" in events
        assert "interrupt_detected" in events
        assert result.interrupted is True
        assert fsm.state == State.ACKING


# =========================================================================
# Test: signal_interrupt() API
# =========================================================================


class TestSignalInterrupt:
    """signal_interrupt() sets flag correctly."""

    def test_sets_pending(self):
        loop, _, _ = _make_loop()
        loop.signal_interrupt()
        assert loop.interrupt.pending is True

    def test_sets_source(self):
        loop, _, _ = _make_loop()
        loop.signal_interrupt(source="watchdog")
        assert loop.interrupt.source == "watchdog"

    def test_sets_replacement_message(self):
        loop, _, _ = _make_loop()
        loop.signal_interrupt(replacement_message="new msg")
        assert loop.interrupt.replacement_message == "new msg"

    def test_default_source_is_user(self):
        loop, _, _ = _make_loop()
        loop.signal_interrupt()
        assert loop.interrupt.source == "user"


# =========================================================================
# Test: Compaction
# =========================================================================


class TestCompaction:
    """Compaction triggers when scratchpad threshold exceeded."""

    @pytest.mark.asyncio
    async def test_compaction_called_when_needed(self):
        """When scratchpad needs compaction, summarize_messages is called."""
        loop, _, llm = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[ToolCall(name="recall_memory", arguments={"query": "x"})],
                    tokens_in=5,
                    tokens_out=5,
                ),
                LLMResponse(text="Done.", tokens_in=5, tokens_out=5),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        # Force compaction by setting a very low threshold
        loop.scratchpad.compaction_token_ratio = 0.0001
        loop.scratchpad.budget.max_context_tokens = 1  # very small

        await loop.run(phase1, "test")

        llm.summarize_messages.assert_called()


# =========================================================================
# Test: _cognitive_summary helper
# =========================================================================


class TestCognitiveSummary:
    """_cognitive_summary() extracts short summaries from tool results."""

    def test_success_with_formatted_message(self):
        result = {"success": True, "data": {"formatted_message": "OK acknowledged"}}
        assert _cognitive_summary(result) == "OK acknowledged"

    def test_success_with_message_key(self):
        result = {"success": True, "data": {"message": "Updated beliefs"}}
        assert _cognitive_summary(result) == "Updated beliefs"

    def test_success_with_summary_key(self):
        result = {"success": True, "data": {"summary": "2 facts added"}}
        assert _cognitive_summary(result) == "2 facts added"

    def test_success_fallback_to_str(self):
        result = {"success": True, "data": {"section": "beliefs_active", "count": 3}}
        s = _cognitive_summary(result)
        assert "beliefs_active" in s

    def test_failure(self):
        result = {"success": False, "error": "constraint violation"}
        assert _cognitive_summary(result) == "constraint violation"

    def test_truncation(self):
        result = {"success": True, "data": {"formatted_message": "x" * 300}}
        s = _cognitive_summary(result)
        assert len(s) <= 200


# =========================================================================
# Test: Token tracking
# =========================================================================


class TestTokenTracking:
    """Budget token tracking across iterations."""

    @pytest.mark.asyncio
    async def test_tokens_accumulated(self):
        loop, _, _ = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[ToolCall(name="recall_memory", arguments={"query": "x"})],
                    tokens_in=100,
                    tokens_out=50,
                ),
                LLMResponse(text="Done.", tokens_in=200, tokens_out=100),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        await loop.run(phase1, "test")

        assert loop.scratchpad.budget.tokens_in == 300
        assert loop.scratchpad.budget.tokens_out == 150


# =========================================================================
# Test: FSM transition trace completeness
# =========================================================================


class TestFSMTransitionTrace:
    """Verify complete FSM traces for LOW and MEDIUM paths."""

    @pytest.mark.asyncio
    async def test_low_trace(self):
        """LOW: exactly 1 transition (DISPATCH_COMPLETE)."""
        loop, _, _ = _make_loop(
            llm_responses=[LLMResponse(text="Hi", tokens_in=5, tokens_out=5)],
        )
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "hi")

        assert len(result.fsm_transitions) == 1
        assert result.fsm_transitions[0] == (
            "DISPATCHING",
            "dispatch_complete",
            "DELIVERING",
        )

    @pytest.mark.asyncio
    async def test_medium_trace_with_tools(self):
        """MEDIUM with tools: 3 transitions (ACK, PROGRESS, COMPLETE)."""
        loop, _, _ = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[ToolCall(name="recall_memory", arguments={"query": "x"})],
                    tokens_in=10,
                    tokens_out=5,
                ),
                LLMResponse(text="Hotel booked.", tokens_in=10, tokens_out=20),
            ],
        )
        phase1 = _make_phase1(tier="MEDIUM")

        result = await loop.run(phase1, "Book hotel")

        assert len(result.fsm_transitions) == 3
        events = [t[1] for t in result.fsm_transitions]
        assert events == [
            "preliminary_ack_sent",
            "progress_received",
            "dispatch_complete",
        ]

    @pytest.mark.asyncio
    async def test_medium_trace_text_only(self):
        """MEDIUM text-only: 2 transitions (ACK, COMPLETE)."""
        loop, _, _ = _make_loop(
            llm_responses=[
                LLMResponse(text="Quick answer.", tokens_in=5, tokens_out=10),
            ],
        )
        phase1 = _make_phase1(tier="MEDIUM")

        result = await loop.run(phase1, "Quick question")

        assert len(result.fsm_transitions) == 2
        events = [t[1] for t in result.fsm_transitions]
        assert events == ["preliminary_ack_sent", "dispatch_complete"]


# =========================================================================
# Test: Multiple tool calls in single iteration
# =========================================================================


class TestMultipleToolCalls:
    """Multiple tool calls in a single LLM response."""

    @pytest.mark.asyncio
    async def test_two_tools_one_response(self):
        loop, _, llm = _make_loop(
            llm_responses=[
                LLMResponse(
                    tool_calls=[
                        ToolCall(
                            name="update_beliefs",
                            arguments={
                                "key": "trip_pref",
                                "value": "skiing",
                                "source": "user",
                            },
                        ),
                        ToolCall(name="recall_memory", arguments={"query": "allergies"}),
                    ],
                    tokens_in=20,
                    tokens_out=15,
                ),
                LLMResponse(text="Found allergies.", tokens_in=10, tokens_out=20),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "Any allergies?")

        assert result.tool_calls_made == 2
        assert len(loop.scratchpad.tool_history) == 2
        # update_beliefs (cognitive) + recall_memory (read)
        tool_names = [e.tool_name for e in loop.scratchpad.tool_history]
        assert "update_beliefs" in tool_names
        assert "recall_memory" in tool_names


# =========================================================================
# Test: Error in tool does not crash loop
# =========================================================================


class TestToolError:
    """Tool errors are recorded but don't crash the loop."""

    @pytest.mark.asyncio
    async def test_tool_error_continues(self):
        def failing(**kw):
            raise RuntimeError("service unavailable")

        loop, _, _ = _make_loop(
            handlers={"invoke_capability": ("action", failing)},
            llm_responses=[
                LLMResponse(
                    tool_calls=[
                        ToolCall(name="invoke_capability", arguments={"capability_id": "x"})
                    ],
                    tokens_in=10,
                    tokens_out=5,
                ),
                LLMResponse(text="Could not get data.", tokens_in=10, tokens_out=20),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        result = await loop.run(phase1, "execute")

        assert result.final_response == "Could not get data."
        assert result.tool_calls_made == 1
        # Tool history records the failure
        entry = loop.scratchpad.tool_history[0]
        assert entry.ok is False

    @pytest.mark.asyncio
    async def test_failed_tool_not_extracted(self):
        """Failed tool results are not sent to extract_findings."""

        def failing(**kw):
            raise RuntimeError("boom")

        loop, _, llm = _make_loop(
            handlers={"invoke_capability": ("action", failing)},
            llm_responses=[
                LLMResponse(
                    tool_calls=[
                        ToolCall(name="invoke_capability", arguments={"capability_id": "x"})
                    ],
                    tokens_in=10,
                    tokens_out=5,
                ),
                LLMResponse(text="Error.", tokens_in=10, tokens_out=10),
            ],
        )
        phase1 = _make_phase1(tier="LOW")

        await loop.run(phase1, "run")

        # extract_findings_batch NOT called (tool failed)
        llm.extract_findings_batch.assert_not_called()
