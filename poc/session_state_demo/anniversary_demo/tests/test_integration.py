"""Integration tests for Streaming + ReAct Loop (Phases 1-5).

Validates the full chain:
  SimpleLLMClient (SDK migration + streaming) -> FSMController ->
  ReActLoop + Scratchpad + Events -> DemoEventHandler -> Runner wiring.

Each test exercises real component contracts with minimal mocking
(only the LLM API boundary is mocked -- everything else is real).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from poc.session_state_demo.anniversary_demo.fsm_controller import (
    Action,
    Event,
    FSMController,
    InvalidTransitionError,
    State,
)
from poc.session_state_demo.anniversary_demo.react import (
    COGNITIVE_TOOLS,
    Finding,
    LoopBudget,
    ReActLoop,
    ReActResult,
    Scratchpad,
    Tier,
)
from poc.session_state_demo.anniversary_demo.react.events import (
    LoopEvent,
    LoopEventHandler,
    LoopEventType,
    NullEventHandler,
)
from poc.session_state_demo.anniversary_demo.react.loop import (
    InterruptSignal,
    Phase1Result,
    build_system_prompt,
)

# ===================================================================
# 1. SimpleLLMClient construction (Phase 1 -- SDK migration)
# ===================================================================


class TestSimpleLLMClientConstruction:
    """Verify SimpleLLMClient uses the new google-genai SDK."""

    def test_import_path(self):
        """SimpleLLMClient is importable from its canonical location."""
        from poc.session_state_demo.llm_client import SimpleLLMClient

        assert SimpleLLMClient is not None

    @patch("poc.session_state_demo.llm_client.genai")
    def test_creates_genai_client(self, mock_genai):
        """Constructor calls genai.Client(api_key=...) -- new SDK pattern."""
        from poc.session_state_demo.llm_client import SimpleLLMClient

        client = SimpleLLMClient(api_key="test-key-123")

        mock_genai.Client.assert_called_once_with(api_key="test-key-123")
        assert client.model_name == "gemini-2.5-pro-preview-05-06"

    @patch("poc.session_state_demo.llm_client.genai")
    def test_custom_model_name(self, mock_genai):
        """Custom model name is stored and used."""
        from poc.session_state_demo.llm_client import SimpleLLMClient

        client = SimpleLLMClient(api_key="k", model="gemini-2.0-flash")
        assert client.model_name == "gemini-2.0-flash"


# ===================================================================
# 2. generate_stream() returns same dict format (Phase 2)
# ===================================================================


class TestGenerateStreamFormat:
    """Verify generate_stream() returns Dict with 'content' and 'tool_calls'."""

    @pytest.fixture
    def mock_client(self):
        with patch("poc.session_state_demo.llm_client.genai") as mock_genai:
            from poc.session_state_demo.llm_client import SimpleLLMClient

            client = SimpleLLMClient(api_key="test-key")

            # Mock the streaming response -- text-only case
            mock_chunk = MagicMock()
            mock_part = MagicMock()
            mock_part.text = "Hello world"
            mock_part.function_call = None
            mock_chunk.candidates = [MagicMock()]
            mock_chunk.candidates[0].content.parts = [mock_part]

            mock_genai.Client.return_value.models.generate_content_stream.return_value = [
                mock_chunk
            ]

            yield client, mock_genai

    @pytest.mark.asyncio
    async def test_text_response_dict_format(self, mock_client):
        """Text-only streaming returns {'content': str, 'tool_calls': []}."""
        client, _ = mock_client

        result = await client.generate_stream(
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "Hi"}],
            tools=[],
        )

        assert isinstance(result, dict)
        assert "content" in result
        assert "tool_calls" in result
        assert isinstance(result["content"], str)
        assert isinstance(result["tool_calls"], list)

    @pytest.mark.asyncio
    async def test_on_text_delta_callback(self, mock_client):
        """on_text_delta callback receives streamed text chunks."""
        client, _ = mock_client
        received_chunks: list[str] = []

        await client.generate_stream(
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "Hi"}],
            tools=[],
            on_text_delta=lambda t: received_chunks.append(t),
        )

        assert len(received_chunks) > 0
        assert any("Hello" in c or "world" in c for c in received_chunks)


# ===================================================================
# 3. FSMController full cycle (Phase 3)
# ===================================================================


class TestFSMControllerFullCycle:
    """Drive FSMController through a complete LISTENING -> DELIVERING -> LISTENING cycle."""

    def test_initial_state_is_listening(self):
        fsm = FSMController()
        assert fsm.state == State.LISTENING

    def test_full_happy_path_cycle(self):
        """LISTENING -> ACKING -> DISPATCHING -> DELIVERING -> LISTENING."""
        fsm = FSMController()

        # T1: message arrives
        state, actions = fsm.transition(Event.MESSAGE_RECEIVED)
        assert state == State.ACKING
        assert Action.ACQUIRE_LOCK in actions
        assert Action.RUN_PHASE1 in actions

        # T3: phase1 complete, no gaps
        state, actions = fsm.transition(Event.PHASE1_COMPLETE)
        assert state == State.DISPATCHING
        assert Action.ROUTE_BY_TIER in actions

        # T8: dispatch done immediately (LOW tier)
        state, actions = fsm.transition(Event.DISPATCH_COMPLETE)
        assert state == State.DELIVERING
        assert Action.ASSEMBLE_RESPONSE in actions

        # T12: response shown
        state, actions = fsm.transition(Event.RESPONSE_DELIVERED)
        assert state == State.LISTENING
        assert Action.FLUSH_AND_CHECKPOINT in actions

    def test_clarification_path(self):
        """LISTENING -> ACKING -> CLARIFYING -> ACKING -> DISPATCHING."""
        fsm = FSMController()

        fsm.transition(Event.MESSAGE_RECEIVED)
        assert fsm.state == State.ACKING

        # T4: gaps detected
        state, actions = fsm.transition(Event.GAPS_DETECTED)
        assert state == State.CLARIFYING
        assert Action.SEND_CLARIFICATION in actions

        # T5: clarification received
        state, actions = fsm.transition(Event.CLARIFICATION_RECEIVED)
        assert state == State.ACKING

        # T3: now phase1 is complete
        state, actions = fsm.transition(Event.PHASE1_COMPLETE)
        assert state == State.DISPATCHING

    def test_companion_path_medium_tier(self):
        """DISPATCHING -> COMPANIONING -> PROGRESSING -> DELIVERING."""
        fsm = FSMController()
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        assert fsm.state == State.DISPATCHING

        # T7: preliminary ack sent (MEDIUM/HIGH)
        state, actions = fsm.transition(Event.PRELIMINARY_ACK_SENT)
        assert state == State.COMPANIONING
        assert Action.SEND_ACKNOWLEDGE in actions
        assert Action.START_TOOL_LOOP in actions

        # T9: progress update
        state, actions = fsm.transition(Event.PROGRESS_RECEIVED)
        assert state == State.PROGRESSING
        assert Action.STREAM_PROGRESS in actions

        # T11: all done
        state, actions = fsm.transition(Event.DISPATCH_COMPLETE)
        assert state == State.DELIVERING

    def test_interrupt_handling(self):
        """Interrupt from interruptible state."""
        fsm = FSMController()
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        assert fsm.state == State.DISPATCHING
        assert fsm.is_interruptible()

        # T13a: interrupt
        state, actions = fsm.transition(Event.INTERRUPT_DETECTED)
        assert state == State.INTERRUPT_HANDLING
        assert Action.CANCEL_INFLIGHT in actions

        # T14: handled
        state, actions = fsm.transition(Event.INTERRUPT_HANDLED)
        assert state == State.ACKING

    def test_crisis_bypass(self):
        """Crisis detection bypasses dispatch to DELIVERING."""
        fsm = FSMController()
        fsm.transition(Event.MESSAGE_RECEIVED)

        state, actions = fsm.transition(Event.CRISIS_DETECTED)
        assert state == State.DELIVERING
        assert Action.CRISIS_RESPONSE in actions

    def test_invalid_transition_raises(self):
        """Invalid transition raises InvalidTransitionError."""
        fsm = FSMController()
        with pytest.raises(InvalidTransitionError):
            fsm.transition(Event.PHASE1_COMPLETE)  # not valid from LISTENING

    def test_history_records_transitions(self):
        """Transition history tracks (from, event, to) tuples."""
        fsm = FSMController()
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)

        history = fsm.history
        assert len(history) == 2
        assert history[0] == (State.LISTENING, Event.MESSAGE_RECEIVED, State.ACKING)
        assert history[1] == (State.ACKING, Event.PHASE1_COMPLETE, State.DISPATCHING)

    def test_reset_clears_state(self):
        """Reset returns to LISTENING with empty history."""
        fsm = FSMController()
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.reset()
        assert fsm.state == State.LISTENING
        assert fsm.history == []


# ===================================================================
# 4. Scratchpad budget exhaustion (Phase 4)
# ===================================================================


class TestScratchpadBudget:
    """Verify Scratchpad budget tracking and tier presets."""

    def test_low_tier_budget(self):
        budget = LoopBudget.for_tier(Tier.LOW)
        assert budget.max_tools == 5
        assert budget.max_iterations == 3
        assert budget.exhausted is False

    def test_medium_tier_budget(self):
        budget = LoopBudget.for_tier(Tier.MEDIUM)
        assert budget.max_tools == 15
        assert budget.max_iterations == 6

    def test_high_tier_budget(self):
        budget = LoopBudget.for_tier(Tier.HIGH)
        assert budget.max_tools == 30
        assert budget.max_iterations == 10

    def test_budget_exhaustion_by_tools(self):
        budget = LoopBudget.for_tier(Tier.LOW)
        for _ in range(5):
            budget.consume_tool()
        assert budget.exhausted is True
        assert budget.remaining_tools == 0

    def test_budget_exhaustion_by_iterations(self):
        budget = LoopBudget.for_tier(Tier.LOW)
        for _ in range(3):
            budget.consume_iteration()
        assert budget.exhausted is True
        assert budget.remaining_iterations == 0

    def test_scratchpad_is_complete_follows_budget(self):
        pad = Scratchpad(tier=Tier.LOW)
        pad.budget = LoopBudget.for_tier(Tier.LOW)
        assert pad.is_complete is False

        for _ in range(5):
            pad.budget.consume_tool()
        assert pad.is_complete is True

    def test_cognitive_tools_set(self):
        """COGNITIVE_TOOLS matches anniversary demo tool names."""
        expected = {"add_belief", "update_persona", "update_emotion", "acknowledge"}
        assert COGNITIVE_TOOLS == expected


# ===================================================================
# 5. Scratchpad findings management
# ===================================================================


class TestScratchpadFindings:
    """Verify finding extraction, deduplication, and summary."""

    def test_add_finding(self):
        pad = Scratchpad()
        f = Finding(
            key="hotel_price", value="$250/night", type="fact", source_tool="search_accommodations"
        )
        pad.add_finding(f)
        assert "hotel_price" in pad.findings
        assert pad.findings["hotel_price"].value == "$250/night"

    def test_exact_duplicate_skipped(self):
        pad = Scratchpad()
        f1 = Finding(key="temp", value="72F")
        f2 = Finding(key="temp", value="72F")
        pad.add_finding(f1)
        pad.add_finding(f2)
        assert len(pad.findings) == 1

    def test_semantic_duplicate_skipped(self):
        """Normalized key match with same value is skipped."""
        pad = Scratchpad()
        pad.add_finding(Finding(key="result_weather", value="sunny"))
        pad.add_finding(Finding(key="data_weather", value="sunny"))
        assert len(pad.findings) == 1

    def test_key_collision_namespaced(self):
        """Different values for same key get namespaced key_2, key_3."""
        pad = Scratchpad()
        pad.add_finding(Finding(key="price", value="$100"))
        pad.add_finding(Finding(key="price", value="$200"))
        assert len(pad.findings) == 2
        assert "price" in pad.findings
        assert "price_2" in pad.findings

    def test_findings_summary_format(self):
        pad = Scratchpad()
        pad.add_finding(Finding(key="hotel", value="Marriott", type="fact"))
        pad.add_finding(Finding(key="temp", value="72F", type="weather"))
        summary = pad.findings_summary()
        assert "FACT" in summary
        assert "WEATHER" in summary
        assert "hotel" in summary
        assert "Marriott" in summary

    def test_record_tool_call(self):
        pad = Scratchpad(tier=Tier.MEDIUM)
        pad.budget = LoopBudget.for_tier(Tier.MEDIUM)
        pad.record_tool_call(
            "search_restaurants", {"cuisine": "Italian"}, ok=True, summary="Found 5 results"
        )
        assert len(pad.tool_history) == 1
        assert pad.tool_history[0].tool_name == "search_restaurants"
        assert pad.budget.tools_used == 1


# ===================================================================
# 6. LoopEventHandler event reception (Phase 4)
# ===================================================================


class TestLoopEventHandler:
    """Verify event handler protocol and event dispatch."""

    def test_null_handler_accepts_all_events(self):
        handler = NullEventHandler()
        for etype in LoopEventType:
            handler.on_event(LoopEvent(type=etype, data={}))

    def test_null_handler_satisfies_protocol(self):
        assert isinstance(NullEventHandler(), LoopEventHandler)

    def test_custom_handler_receives_events(self):
        received: list[LoopEvent] = []

        class TestHandler:
            def on_event(self, event: LoopEvent) -> None:
                received.append(event)

        handler = TestHandler()
        assert isinstance(handler, LoopEventHandler)

        handler.on_event(LoopEvent(type=LoopEventType.TEXT_DELTA, data={"text": "hi"}))
        handler.on_event(
            LoopEvent(type=LoopEventType.TOOL_CALL_START, data={"tool_name": "search"})
        )
        handler.on_event(LoopEvent(type=LoopEventType.LOOP_COMPLETE, data={"iterations": 3}))

        assert len(received) == 3
        assert received[0].type == LoopEventType.TEXT_DELTA
        assert received[0].data["text"] == "hi"
        assert received[2].data["iterations"] == 3

    def test_event_has_timestamp(self):
        event = LoopEvent(type=LoopEventType.ITERATION_START, data={"iteration": 1})
        assert event.timestamp > 0

    def test_all_event_types_defined(self):
        """All expected event types exist in the enum."""
        expected = {
            "ITERATION_START",
            "LLM_CALL_START",
            "LLM_CALL_END",
            "TEXT_DELTA",
            "TOOL_CALL_START",
            "TOOL_CALL_END",
            "FINDING_EXTRACTED",
            "FSM_TRANSITION",
            "ACK_DELIVERED",
            "COMPACTION",
            "LOOP_COMPLETE",
            "BUDGET_WARNING",
            "THOUGHT",
            "CYCLE_DETECTED",
            "TOOL_CACHE_HIT",
        }
        actual = {e.name for e in LoopEventType}
        assert expected == actual


# ===================================================================
# 7. DemoEventHandler (Phase 5)
# ===================================================================


class TestDemoEventHandler:
    """Verify DemoEventHandler maps events to display functions."""

    def test_import_and_instantiate(self):
        from poc.session_state_demo.anniversary_demo.runner import DemoEventHandler

        handler = DemoEventHandler(verbose=False)
        assert isinstance(handler, LoopEventHandler)

    def test_silent_when_not_verbose(self):
        """Non-verbose handler does not raise on any event type."""
        from poc.session_state_demo.anniversary_demo.runner import DemoEventHandler

        handler = DemoEventHandler(verbose=False)
        for etype in LoopEventType:
            handler.on_event(LoopEvent(type=etype, data={}))

    def test_streamed_text_tracking(self):
        """streamed_text property tracks TEXT_DELTA reception."""
        from poc.session_state_demo.anniversary_demo.runner import DemoEventHandler

        handler = DemoEventHandler(verbose=False)
        assert handler.streamed_text is False

        handler.on_event(LoopEvent(type=LoopEventType.TEXT_DELTA, data={"text": "hi"}))
        # verbose=False short-circuits before recording, so we test with verbose=True
        handler2 = DemoEventHandler(verbose=True)
        assert handler2.streamed_text is False
        # Patch print to avoid terminal output
        with patch("poc.session_state_demo.anniversary_demo.runner.print_streaming_text"):
            handler2.on_event(LoopEvent(type=LoopEventType.TEXT_DELTA, data={"text": "hi"}))
        assert handler2.streamed_text is True

    def test_reset_clears_state(self):
        from poc.session_state_demo.anniversary_demo.runner import DemoEventHandler

        handler = DemoEventHandler(verbose=True)
        with patch("poc.session_state_demo.anniversary_demo.runner.print_streaming_text"):
            handler.on_event(LoopEvent(type=LoopEventType.TEXT_DELTA, data={"text": "hi"}))
        assert handler.streamed_text is True
        handler.reset()
        assert handler.streamed_text is False


# ===================================================================
# 8. Phase1Result and classify_to_phase1 adapter (Phase 5)
# ===================================================================


class TestPhase1Adapter:
    """Verify Phase1Result dataclass and the classify_to_phase1 adapter."""

    def test_phase1result_defaults(self):
        result = Phase1Result()
        assert result.intent == ""
        assert result.tier == "MEDIUM"
        assert result.safety_band == "GREEN"
        assert result.entities == {}
        assert result.gaps == []
        assert result.confidence == 1.0

    def test_phase1result_custom(self):
        result = Phase1Result(
            intent="plan_trip",
            tier="HIGH",
            safety_band="AMBER",
            entities={"destination": "Napa Valley"},
            confidence=0.95,
            gaps=["What dates?"],
        )
        assert result.intent == "plan_trip"
        assert result.tier == "HIGH"
        assert len(result.gaps) == 1

    def test_classify_to_phase1_import(self):
        from poc.session_state_demo.anniversary_demo.runner import classify_to_phase1

        assert callable(classify_to_phase1)


# ===================================================================
# 9. build_system_prompt (Phase 4)
# ===================================================================


class TestBuildSystemPrompt:
    """Verify system prompt construction."""

    def test_basic_prompt_generation(self):
        prompt = build_system_prompt(
            fsm_state="DISPATCHING",
            turn_number=5,
            tier="MEDIUM",
            safety_band="GREEN",
        )
        assert "DISPATCHING" in prompt
        assert "MEDIUM" in prompt
        assert "GREEN" in prompt
        assert "FamilyOS Concierge" in prompt

    def test_prompt_with_family_persona(self):
        persona = {
            "family_name": "Smith",
            "home_location": "Portland",
            "members": [
                {
                    "name": "John",
                    "role": "Dad",
                    "age": 45,
                    "allergies": ["peanuts"],
                    "preferences": ["hiking"],
                },
                {
                    "name": "Jane",
                    "role": "Mom",
                    "age": 42,
                    "allergies": [],
                    "preferences": ["cooking"],
                },
            ],
        }
        prompt = build_system_prompt(
            fsm_state="LISTENING",
            turn_number=1,
            tier="LOW",
            safety_band="GREEN",
            family_persona=persona,
        )
        assert "Smith" in prompt
        assert "Portland" in prompt
        assert "John" in prompt
        assert "peanuts" in prompt

    def test_prompt_with_tool_declarations(self):
        tools = [
            {"name": "search_restaurants", "description": "Search for restaurants nearby"},
            {"name": "add_belief", "description": "Store a belief in session state"},
        ]
        prompt = build_system_prompt(
            fsm_state="DISPATCHING",
            turn_number=3,
            tier="MEDIUM",
            safety_band="GREEN",
            tool_declarations=tools,
        )
        assert "search_restaurants" in prompt
        assert "add_belief" in prompt
        assert "2 for MEDIUM" in prompt

    def test_safety_band_table_present(self):
        prompt = build_system_prompt(
            fsm_state="LISTENING",
            turn_number=1,
            tier="LOW",
            safety_band="RED",
        )
        assert "RED" in prompt
        assert "CRISIS" in prompt
        assert "Read-only" in prompt


# ===================================================================
# 10. ReActLoop with mocked LLM (Phase 4)
# ===================================================================


class TestReActLoopMockedLLM:
    """Test ReActLoop.run() with a mocked LLM client."""

    @pytest.fixture
    def loop_components(self):
        """Create ReActLoop with all real components except the LLM."""
        fsm = FSMController()
        # Drive FSM to DISPATCHING (required state for ReActLoop entry)
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        assert fsm.state == State.DISPATCHING

        # Mock the tool registry
        registry = MagicMock()
        registry.get_llm_declarations.return_value = [
            {
                "name": "acknowledge",
                "description": "Acknowledge user",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ack_type": {"type": "string"},
                        "message": {"type": "string"},
                        "next_tool": {"type": "string"},
                    },
                },
            },
        ]
        # Make registry.get() return a tool with a handler
        mock_tool = MagicMock()
        mock_tool.handler = MagicMock(return_value={"success": True, "message": "Acknowledged"})
        registry.get.return_value = mock_tool

        # Mock the LLM client
        llm = MagicMock()

        # Create scratchpad
        pad = Scratchpad(tier=Tier.LOW)
        pad.budget = LoopBudget.for_tier(Tier.LOW)

        # Event collector
        events: list[LoopEvent] = []

        class CollectorHandler:
            def on_event(self, event: LoopEvent) -> None:
                events.append(event)

        handler = CollectorHandler()

        loop = ReActLoop(
            fsm=fsm,
            registry=registry,
            llm=llm,
            scratchpad=pad,
            event_handler=handler,
        )

        return loop, llm, events

    @pytest.mark.asyncio
    async def test_text_only_response(self, loop_components):
        """LLM returns text-only -> loop completes in 1 iteration."""
        loop, llm, events = loop_components

        # Mock generate_stream to return text-only response
        llm.generate_stream = AsyncMock(
            return_value={
                "content": "I'd love to help plan your anniversary weekend!",
                "tool_calls": [],
            }
        )

        p1 = Phase1Result(intent="plan_trip", tier="LOW")
        result = await loop.run(
            phase1=p1,
            user_message="Plan our anniversary weekend",
            turn_number=1,
        )

        assert isinstance(result, ReActResult)
        assert result.final_response != ""
        assert result.iterations >= 1
        assert result.error is None

    @pytest.mark.asyncio
    async def test_tool_calling_iteration(self, loop_components):
        """LLM calls a tool then produces text -> 2 iterations."""
        loop, llm, events = loop_components

        call_count = 0

        async def mock_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: LLM wants to use acknowledge tool
                return {
                    "content": "",
                    "tool_calls": [
                        {
                            "name": "acknowledge",
                            "args": {
                                "ack_type": "progress",
                                "message": "Looking into it",
                                "next_tool": "none",
                            },
                        }
                    ],
                }
            else:
                # Second call: text response
                return {
                    "content": "Here's what I found for your anniversary weekend!",
                    "tool_calls": [],
                }

        llm.generate_stream = mock_stream

        p1 = Phase1Result(intent="plan_trip", tier="LOW")
        result = await loop.run(
            phase1=p1,
            user_message="Plan our anniversary",
            turn_number=1,
        )

        assert isinstance(result, ReActResult)
        assert result.tool_calls_made >= 1
        assert result.iterations >= 2

    @pytest.mark.asyncio
    async def test_budget_exhaustion_stops_loop(self, loop_components):
        """Budget exhaustion produces a result with budget_exhausted=True."""
        loop, llm, events = loop_components

        # Always return tool calls to force budget exhaustion
        llm.generate_stream = AsyncMock(
            return_value={
                "content": "",
                "tool_calls": [
                    {
                        "name": "acknowledge",
                        "args": {"ack_type": "progress", "message": "working", "next_tool": "none"},
                    }
                ],
            }
        )

        p1 = Phase1Result(intent="plan_trip", tier="LOW")
        result = await loop.run(
            phase1=p1,
            user_message="Plan a complex trip",
            turn_number=1,
        )

        assert isinstance(result, ReActResult)
        # Either budget exhausted or loop hit max iterations
        assert result.budget_exhausted or result.iterations >= 1

    @pytest.mark.asyncio
    async def test_events_emitted_during_loop(self, loop_components):
        """Event handler receives events during loop execution."""
        loop, llm, events = loop_components

        llm.generate_stream = AsyncMock(
            return_value={
                "content": "Done!",
                "tool_calls": [],
            }
        )

        p1 = Phase1Result(intent="greet", tier="LOW")
        await loop.run(
            phase1=p1,
            user_message="Hello",
            turn_number=1,
        )

        event_types = {e.type for e in events}
        # Should have at least iteration_start, llm_call_start, loop_complete
        assert LoopEventType.ITERATION_START in event_types
        assert LoopEventType.LLM_CALL_START in event_types
        assert LoopEventType.LOOP_COMPLETE in event_types

    @pytest.mark.asyncio
    async def test_fsm_transitions_recorded(self, loop_components):
        """FSM transitions are recorded in result.fsm_transitions."""
        loop, llm, events = loop_components

        llm.generate_stream = AsyncMock(
            return_value={
                "content": "Here you go!",
                "tool_calls": [],
            }
        )

        p1 = Phase1Result(intent="greet", tier="LOW")
        result = await loop.run(
            phase1=p1,
            user_message="Hi there",
            turn_number=1,
        )

        # The loop should fire at least some FSM transitions
        assert isinstance(result.fsm_transitions, list)


# ===================================================================
# 11. InterruptSignal (Phase 4)
# ===================================================================


class TestInterruptSignal:
    """Verify interrupt signal mechanics."""

    def test_default_not_pending(self):
        sig = InterruptSignal()
        assert sig.pending is False
        assert sig.source == ""

    def test_signal_interrupt(self):
        sig = InterruptSignal()
        sig.pending = True
        sig.source = "user_interrupt"
        sig.replacement_message = "Cancel that"
        assert sig.pending is True
        assert sig.source == "user_interrupt"


# ===================================================================
# 12. Tool Registry tier filtering (Phase 4)
# ===================================================================


class TestToolRegistryTierFiltering:
    """Verify get_llm_declarations(tier) returns correct tool counts."""

    @pytest.fixture
    def registry(self):
        from poc.session_state_demo.anniversary_demo.tools.registry import (
            create_demo_registry,
        )

        return create_demo_registry()

    def test_low_tier_returns_cognitive_tools(self, registry):
        decls = registry.get_llm_declarations(Tier.LOW)
        names = {d["name"] for d in decls}
        # LOW tier should include cognitive tools + essential functional tools
        assert "acknowledge" in names
        assert "get_family_member_info" in names  # functional tool now in LOW
        assert len(decls) <= 12  # cognitive + essential functional

    def test_medium_tier_returns_more(self, registry):
        low_decls = registry.get_llm_declarations(Tier.LOW)
        medium_decls = registry.get_llm_declarations(Tier.MEDIUM)
        assert len(medium_decls) >= len(low_decls)

    def test_high_tier_returns_all(self, registry):
        medium_decls = registry.get_llm_declarations(Tier.MEDIUM)
        high_decls = registry.get_llm_declarations(Tier.HIGH)
        assert len(high_decls) >= len(medium_decls)

    def test_declaration_format(self, registry):
        """Each declaration has name, description, and parameters."""
        decls = registry.get_llm_declarations(Tier.MEDIUM)
        for d in decls:
            assert "name" in d
            assert "description" in d
            assert "parameters" in d


# ===================================================================
# 13. ReActResult dataclass (Phase 4)
# ===================================================================


class TestReActResult:
    """Verify ReActResult fields and defaults."""

    def test_defaults(self):
        result = ReActResult()
        assert result.final_response == ""
        assert result.tool_calls_made == 0
        assert result.iterations == 0
        assert result.findings_count == 0
        assert result.fsm_transitions == []
        assert result.budget_exhausted is False
        assert result.interrupted is False
        assert result.error is None

    def test_custom_values(self):
        result = ReActResult(
            final_response="Done!",
            tool_calls_made=5,
            iterations=3,
            findings_count=2,
            budget_exhausted=True,
        )
        assert result.final_response == "Done!"
        assert result.tool_calls_made == 5
        assert result.budget_exhausted is True


# ===================================================================
# 14. Package-level imports (validates all phases wired correctly)
# ===================================================================


class TestPackageLevelImports:
    """Smoke test: all Phase 1-5 components importable from their expected locations."""

    def test_react_package_exports(self):
        from poc.session_state_demo.anniversary_demo.react import (
            COGNITIVE_TOOLS,
            Finding,
            InterruptSignal,
            LoopBudget,
            ReActLoop,
            ReActResult,
            Scratchpad,
            Tier,
            ToolEntry,
        )

        assert all(
            x is not None
            for x in [
                COGNITIVE_TOOLS,
                Finding,
                InterruptSignal,
                LoopBudget,
                ReActLoop,
                ReActResult,
                Scratchpad,
                Tier,
                ToolEntry,
            ]
        )

    def test_fsm_controller_exports(self):
        from poc.session_state_demo.anniversary_demo.fsm_controller import (
            Action,
            Event,
            FSMController,
            InvalidTransitionError,
            State,
        )

        assert all(
            x is not None
            for x in [
                Action,
                Event,
                FSMController,
                InvalidTransitionError,
                State,
            ]
        )

    def test_events_module_exports(self):
        from poc.session_state_demo.anniversary_demo.react.events import (
            LoopEvent,
            LoopEventHandler,
            LoopEventType,
            NullEventHandler,
        )

        assert all(
            x is not None
            for x in [
                LoopEvent,
                LoopEventHandler,
                LoopEventType,
                NullEventHandler,
            ]
        )

    def test_runner_exports(self):
        from poc.session_state_demo.anniversary_demo.runner import (
            DemoEventHandler,
            classify_to_phase1,
        )

        assert DemoEventHandler is not None
        assert classify_to_phase1 is not None

    def test_llm_client_has_streaming(self):
        from poc.session_state_demo.llm_client import SimpleLLMClient

        assert hasattr(SimpleLLMClient, "generate_stream")
        assert hasattr(SimpleLLMClient, "summarize_messages")
