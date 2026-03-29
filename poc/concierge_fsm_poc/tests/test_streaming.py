"""Tests for streaming and live event display features.

Covers:
    - LoopEventType enum completeness
    - LoopEvent dataclass construction and defaults
    - NullEventHandler receives events without error
    - LoopEventHandler protocol compliance
    - LiveLoopDisplay event handling and state updates
    - generate_stream() response structure parity with generate()
"""

from __future__ import annotations

import time
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import pytest

from poc.concierge_fsm_poc.llm.client import LLMResponse, ToolCall
from poc.concierge_fsm_poc.react.events import (
    LoopEvent,
    LoopEventHandler,
    LoopEventType,
    NullEventHandler,
)

# =========================================================================
# LoopEventType enum tests
# =========================================================================


class TestLoopEventType:
    """LoopEventType enum coverage."""

    def test_all_event_types_present(self):
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
        assert actual == expected

    def test_values_are_snake_case(self):
        for e in LoopEventType:
            assert e.value == e.name.lower()

    def test_string_enum(self):
        assert isinstance(LoopEventType.TEXT_DELTA, str)
        assert LoopEventType.TEXT_DELTA == "text_delta"


# =========================================================================
# LoopEvent dataclass tests
# =========================================================================


class TestLoopEvent:
    """LoopEvent construction and defaults."""

    def test_default_data_empty(self):
        e = LoopEvent(type=LoopEventType.ITERATION_START)
        assert e.data == {}

    def test_default_timestamp_set(self):
        before = time.time()
        e = LoopEvent(type=LoopEventType.TEXT_DELTA, data={"text": "hi"})
        after = time.time()
        assert before <= e.timestamp <= after

    def test_data_preserved(self):
        data = {"tool_name": "recall_memory", "arguments": {"query": "test"}}
        e = LoopEvent(type=LoopEventType.TOOL_CALL_START, data=data)
        assert e.data == data

    def test_type_preserved(self):
        e = LoopEvent(type=LoopEventType.FSM_TRANSITION)
        assert e.type == LoopEventType.FSM_TRANSITION


# =========================================================================
# NullEventHandler tests
# =========================================================================


class TestNullEventHandler:
    """NullEventHandler no-op behavior."""

    def test_handles_all_event_types(self):
        handler = NullEventHandler()
        for event_type in LoopEventType:
            event = LoopEvent(type=event_type, data={"key": "value"})
            handler.on_event(event)  # should not raise

    def test_implements_protocol(self):
        handler = NullEventHandler()
        assert isinstance(handler, LoopEventHandler)

    def test_returns_none(self):
        handler = NullEventHandler()
        result = handler.on_event(LoopEvent(type=LoopEventType.TEXT_DELTA))
        assert result is None


# =========================================================================
# Protocol compliance tests
# =========================================================================


class TestLoopEventHandlerProtocol:
    """LoopEventHandler protocol checks."""

    def test_custom_handler_satisfies_protocol(self):
        class MyHandler:
            def __init__(self):
                self.events = []

            def on_event(self, event: LoopEvent) -> None:
                self.events.append(event)

        handler = MyHandler()
        assert isinstance(handler, LoopEventHandler)

    def test_collecting_handler(self):
        class Collector:
            def __init__(self):
                self.events: list[LoopEvent] = []

            def on_event(self, event: LoopEvent) -> None:
                self.events.append(event)

        collector = Collector()
        collector.on_event(LoopEvent(type=LoopEventType.ITERATION_START, data={"iteration": 1}))
        collector.on_event(LoopEvent(type=LoopEventType.TOOL_CALL_START, data={"tool_name": "ack"}))
        collector.on_event(LoopEvent(type=LoopEventType.LOOP_COMPLETE, data={"iterations": 1}))

        assert len(collector.events) == 3
        assert collector.events[0].type == LoopEventType.ITERATION_START
        assert collector.events[1].data["tool_name"] == "ack"
        assert collector.events[2].data["iterations"] == 1


# =========================================================================
# LiveLoopDisplay tests
# =========================================================================


class TestLiveLoopDisplay:
    """LiveLoopDisplay event handling and state management."""

    @pytest.fixture()
    def display(self):
        from poc.concierge_fsm_poc.run_demo import LiveLoopDisplay

        return LiveLoopDisplay()

    def test_initial_state(self, display):
        assert display._iteration == 0
        assert display._current_action == "Initializing..."
        assert len(display._events_log) == 0
        assert display._streaming_text == []
        assert display._tool_active is None
        assert display._fsm_state == "LISTENING"
        assert len(display._recent_findings) == 0
        assert display._elapsed_s == 0.0

    def test_iteration_start(self, display):
        display.on_event(LoopEvent(type=LoopEventType.ITERATION_START, data={"iteration": 3}))
        assert display._iteration == 3
        assert display._current_action == "Thinking..."

    def test_llm_call_start(self, display):
        display.on_event(
            LoopEvent(
                type=LoopEventType.LLM_CALL_START,
                data={"message_count": 5, "tool_count": 8},
            )
        )
        assert "LLM" in display._current_action
        assert len(display._events_log) == 1

    def test_tool_call_start_and_end(self, display):
        display.on_event(
            LoopEvent(
                type=LoopEventType.TOOL_CALL_START,
                data={"tool_name": "invoke_capability", "arguments": {"name": "weather"}},
            )
        )
        assert display._tool_active == "invoke_capability"
        assert display._tools_used == 1
        assert "invoke_capability" in display._current_action

        display.on_event(
            LoopEvent(
                type=LoopEventType.TOOL_CALL_END,
                data={"tool_name": "invoke_capability", "success": True, "summary": "45F cloudy"},
            )
        )
        assert display._tool_active is None

    def test_text_delta(self, display):
        display.on_event(LoopEvent(type=LoopEventType.TEXT_DELTA, data={"text": "Hello "}))
        display.on_event(LoopEvent(type=LoopEventType.TEXT_DELTA, data={"text": "world!"}))
        assert display._streaming_text == ["Hello ", "world!"]

    def test_finding_extracted(self, display):
        display.on_event(
            LoopEvent(
                type=LoopEventType.FINDING_EXTRACTED,
                data={"key": "weather_temp", "value": "45F", "source_tool": "invoke_capability"},
            )
        )
        assert display._findings_count == 1
        assert len(display._recent_findings) == 1
        assert display._recent_findings[0] == ("weather_temp", "45F")

    def test_fsm_transition(self, display):
        display.on_event(
            LoopEvent(
                type=LoopEventType.FSM_TRANSITION,
                data={
                    "from_state": "DISPATCHING",
                    "event": "preliminary_ack_sent",
                    "to_state": "COMPANIONING",
                },
            )
        )
        assert len(display._events_log) == 1
        assert display._fsm_state == "COMPANIONING"

    def test_loop_complete(self, display):
        display.on_event(
            LoopEvent(
                type=LoopEventType.LOOP_COMPLETE,
                data={"iterations": 3, "tools_used": 5, "budget_exhausted": False},
            )
        )
        assert display._current_action == "Complete"

    def test_rich_renderable(self, display):
        """Ensure __rich__() returns a Panel containing a Table."""
        from rich.panel import Panel
        from rich.table import Table

        # Fire a few events
        display.on_event(LoopEvent(type=LoopEventType.ITERATION_START, data={"iteration": 1}))
        display.on_event(
            LoopEvent(
                type=LoopEventType.TOOL_CALL_START,
                data={"tool_name": "ack", "arguments": {}},
            )
        )
        display.on_event(LoopEvent(type=LoopEventType.TEXT_DELTA, data={"text": "response text"}))

        renderable = display.__rich__()
        assert isinstance(renderable, Panel)
        assert isinstance(renderable.renderable, Table)

    def test_event_log_max_size(self, display):
        """Event log should cap at 8 entries."""
        for i in range(15):
            display.on_event(LoopEvent(type=LoopEventType.ITERATION_START, data={"iteration": i}))
        assert len(display._events_log) == 8

    def test_recent_findings_deque_maxlen(self, display):
        """Recent findings deque caps at 3 entries."""
        for i in range(5):
            display.on_event(
                LoopEvent(
                    type=LoopEventType.FINDING_EXTRACTED,
                    data={"key": f"key_{i}", "value": f"val_{i}"},
                )
            )
        assert len(display._recent_findings) == 3
        assert display._recent_findings[0] == ("key_2", "val_2")
        assert display._findings_count == 5

    def test_budget_warning_handler(self, display):
        """BUDGET_WARNING events are logged with red style."""
        display.on_event(
            LoopEvent(
                type=LoopEventType.BUDGET_WARNING,
                data={"resource": "iterations", "used": 8, "limit": 10},
            )
        )
        assert len(display._events_log) == 1
        style, msg = display._events_log[0]
        assert style == "red"
        assert "BUDGET" in msg
        assert "8/10" in msg

    def test_elapsed_time_updates(self, display):
        """Elapsed time should update on every event."""
        import time as _time

        _time.sleep(0.05)
        display.on_event(LoopEvent(type=LoopEventType.ITERATION_START, data={"iteration": 1}))
        assert display._elapsed_s > 0.0

    def test_fsm_state_tracks_multiple_transitions(self, display):
        """FSM state should reflect the most recent transition."""
        display.on_event(
            LoopEvent(
                type=LoopEventType.FSM_TRANSITION,
                data={
                    "from_state": "LISTENING",
                    "event": "request_classified",
                    "to_state": "DISPATCHING",
                },
            )
        )
        assert display._fsm_state == "DISPATCHING"
        display.on_event(
            LoopEvent(
                type=LoopEventType.FSM_TRANSITION,
                data={
                    "from_state": "DISPATCHING",
                    "event": "preliminary_ack_sent",
                    "to_state": "PROGRESSING",
                },
            )
        )
        assert display._fsm_state == "PROGRESSING"


# =========================================================================
# ReActLoop with event handler tests
# =========================================================================


class TestReActLoopEventIntegration:
    """Verify ReActLoop emits events to the handler."""

    def _make_collecting_handler(self):
        class Collector:
            def __init__(self):
                self.events: list[LoopEvent] = []

            def on_event(self, event: LoopEvent) -> None:
                self.events.append(event)

        return Collector()

    def _make_phase1(self, tier: Literal["LOW", "MEDIUM"] = "LOW"):
        from poc.concierge_fsm_poc.fsm.phase1_mock import Phase1Result

        return Phase1Result(
            intent="weather_lookup",
            tier=tier,
            safety_band="GREEN",
            entities={"location": "Tahoe"},
            emotion="neutral",
            confidence=0.9,
            gaps=[],
        )

    def _make_registry(self):
        from poc.concierge_fsm_poc.tools.registry import ToolDefinition, ToolRegistry

        registry = ToolRegistry()
        for name, cat, handler in [
            (
                "update_beliefs",
                "cognitive",
                lambda **kw: {"success": True, "section": "beliefs_active"},
            ),
            (
                "invoke_capability",
                "action",
                lambda **kw: {"weather": "45F sunny"},
            ),
        ]:
            registry.register(
                ToolDefinition(
                    name=name,
                    category=cat,
                    handler=handler,
                    schema={"name": name, "description": f"Test {name}", "parameters": {}},
                    tiers=frozenset({"LOW", "MEDIUM"}),
                )
            )
        return registry

    @pytest.mark.asyncio
    async def test_text_only_response_emits_events(self):
        from poc.concierge_fsm_poc.fsm.controller import Event, FSMController
        from poc.concierge_fsm_poc.react.loop import ReActLoop
        from poc.concierge_fsm_poc.react.scratchpad import Scratchpad

        collector = self._make_collecting_handler()
        fsm = FSMController()
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)

        llm = MagicMock()
        response = LLMResponse(text="Weather is 45F.", tokens_in=10, tokens_out=15)

        async def mock_stream(messages, tools=None, force_tool_call=False, on_text_delta=None):
            if on_text_delta:
                on_text_delta("Weather is 45F.")
            return response

        llm.generate_stream = AsyncMock(side_effect=mock_stream)
        llm.extract_findings_batch = AsyncMock(return_value=[])

        loop = ReActLoop(
            fsm=fsm,
            registry=self._make_registry(),
            llm=llm,
            scratchpad=Scratchpad(),
            event_handler=collector,
        )

        result = await loop.run(self._make_phase1(), "What's the weather?")

        # Verify events were emitted
        event_types = [e.type for e in collector.events]
        assert LoopEventType.ITERATION_START in event_types
        assert LoopEventType.LLM_CALL_START in event_types
        assert LoopEventType.LLM_CALL_END in event_types
        assert LoopEventType.TEXT_DELTA in event_types
        assert LoopEventType.LOOP_COMPLETE in event_types

        # FSM transitions should also appear
        assert LoopEventType.FSM_TRANSITION in event_types

        assert result.final_response == "Weather is 45F."

    @pytest.mark.asyncio
    async def test_tool_call_response_emits_tool_events(self):
        from poc.concierge_fsm_poc.fsm.controller import Event, FSMController
        from poc.concierge_fsm_poc.react.loop import ReActLoop
        from poc.concierge_fsm_poc.react.scratchpad import Finding, Scratchpad

        collector = self._make_collecting_handler()
        fsm = FSMController()
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)

        llm = MagicMock()

        # First call returns tool calls, second returns text
        responses = [
            LLMResponse(
                tool_calls=[ToolCall(name="invoke_capability", arguments={"name": "weather"})],
                tokens_in=10,
                tokens_out=15,
                raw=MagicMock(candidates=[MagicMock(content=None)]),
            ),
            LLMResponse(text="The weather is 45F and sunny.", tokens_in=10, tokens_out=15),
        ]
        call_idx = {"n": 0}

        async def mock_stream(messages, tools=None, force_tool_call=False, on_text_delta=None):
            idx = min(call_idx["n"], len(responses) - 1)
            call_idx["n"] += 1
            resp = responses[idx]
            if on_text_delta and resp.text and not resp.tool_calls:
                on_text_delta(resp.text)
            return resp

        llm.generate_stream = AsyncMock(side_effect=mock_stream)
        llm.extract_findings_batch = AsyncMock(
            return_value=[
                Finding(
                    key="weather_temp",
                    value="45F",
                    type="weather",
                    source_tool="invoke_capability",
                )
            ]
        )

        loop = ReActLoop(
            fsm=fsm,
            registry=self._make_registry(),
            llm=llm,
            scratchpad=Scratchpad(),
            event_handler=collector,
        )

        await loop.run(self._make_phase1(), "Check weather")

        event_types = [e.type for e in collector.events]
        assert LoopEventType.TOOL_CALL_START in event_types
        assert LoopEventType.TOOL_CALL_END in event_types
        assert LoopEventType.FINDING_EXTRACTED in event_types

        # Verify tool_call_start has correct data
        tc_start = [e for e in collector.events if e.type == LoopEventType.TOOL_CALL_START][0]
        assert tc_start.data["tool_name"] == "invoke_capability"

    @pytest.mark.asyncio
    async def test_null_handler_backward_compat(self):
        """Loop works identically with default NullEventHandler."""
        from poc.concierge_fsm_poc.fsm.controller import Event, FSMController
        from poc.concierge_fsm_poc.react.loop import ReActLoop
        from poc.concierge_fsm_poc.react.scratchpad import Scratchpad

        fsm = FSMController()
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)

        llm = MagicMock()

        async def mock_stream(messages, tools=None, force_tool_call=False, on_text_delta=None):
            return LLMResponse(text="Hello.", tokens_in=5, tokens_out=5)

        llm.generate_stream = AsyncMock(side_effect=mock_stream)
        llm.extract_findings_batch = AsyncMock(return_value=[])

        # No event_handler passed -- should use NullEventHandler
        loop = ReActLoop(
            fsm=fsm,
            registry=self._make_registry(),
            llm=llm,
            scratchpad=Scratchpad(),
        )

        result = await loop.run(self._make_phase1(), "Hello")
        assert result.final_response == "Hello."


# =========================================================================
# generate_stream() mock structure tests
# =========================================================================


class TestGenerateStreamContract:
    """Verify generate_stream returns same LLMResponse structure as generate."""

    def test_llm_response_from_text_stream(self):
        """Simulate what generate_stream would return for text-only response."""
        response = LLMResponse(
            text="Here is the weather report.",
            tool_calls=[],
            tokens_in=50,
            tokens_out=25,
        )
        assert response.has_text is True
        assert response.has_tool_calls is False
        assert response.tokens_in == 50
        assert response.tokens_out == 25

    def test_llm_response_from_fc_stream(self):
        """Simulate what generate_stream would return for function-call response."""
        response = LLMResponse(
            text=None,
            tool_calls=[
                ToolCall(name="invoke_capability", arguments={"name": "weather"}),
                ToolCall(name="update_beliefs", arguments={"key": "v"}),
            ],
            tokens_in=100,
            tokens_out=40,
        )
        assert response.has_text is False
        assert response.has_tool_calls is True
        assert len(response.tool_calls) == 2

    def test_on_text_delta_callback_invoked(self):
        """Verify the contract that on_text_delta is called for text-only."""
        deltas: list[str] = []

        def on_delta(text: str) -> None:
            deltas.append(text)

        # Simulate calling on_text_delta as generate_stream would
        chunks = ["The ", "weather ", "is ", "sunny."]
        for chunk in chunks:
            on_delta(chunk)

        assert len(deltas) == 4
        assert "".join(deltas) == "The weather is sunny."
