"""ReAct Loop Event Protocol -- Live visibility into loop execution.

Defines a callback protocol that the ReAct loop uses to emit real-time
events (tool calls, findings, FSM transitions, streaming text) to the
display layer.  The display layer (e.g. Rich Live panel in run_demo.py)
implements ``LoopEventHandler`` to render these events as they happen.

Separation of concerns:
    - ``react/loop.py`` emits events via ``_emit()``
    - ``run_demo.py`` receives events via ``LiveLoopDisplay``
    - This module defines the shared contract between them.

Files: ``react/events.py``
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class LoopEventType(str, Enum):
    """Types of events emitted by the ReAct loop."""

    ITERATION_START = "iteration_start"
    LLM_CALL_START = "llm_call_start"
    LLM_CALL_END = "llm_call_end"
    TEXT_DELTA = "text_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    FINDING_EXTRACTED = "finding_extracted"
    FSM_TRANSITION = "fsm_transition"
    ACK_DELIVERED = "ack_delivered"
    COMPACTION = "compaction"
    LOOP_COMPLETE = "loop_complete"
    BUDGET_WARNING = "budget_warning"
    THOUGHT = "thought"
    CYCLE_DETECTED = "cycle_detected"
    TOOL_CACHE_HIT = "tool_cache_hit"


# ---------------------------------------------------------------------------
# Event data container
# ---------------------------------------------------------------------------


@dataclass
class LoopEvent:
    """A single event emitted by the ReAct loop.

    Parameters
    ----------
    type:
        The kind of event (see ``LoopEventType``).
    data:
        Event-specific payload.  Keys vary by type:

        ITERATION_START:   {iteration: int}
        LLM_CALL_START:    {message_count: int, tool_count: int}
        LLM_CALL_END:      {has_tool_calls: bool, tokens_in: int, tokens_out: int}
        TEXT_DELTA:         {text: str}
        TOOL_CALL_START:   {tool_name: str, arguments: dict}
        TOOL_CALL_END:     {tool_name: str, success: bool, summary: str}
        FINDING_EXTRACTED: {key: str, value: str, source_tool: str}
        FSM_TRANSITION:    {from_state: str, event: str, to_state: str}
        ACK_DELIVERED:     {message: str}
        COMPACTION:        {summary_len: int}
        LOOP_COMPLETE:     {iterations: int, tools_used: int, budget_exhausted: bool}
        BUDGET_WARNING:    {resource: str, used: int, limit: int}
        THOUGHT:           {text: str, iteration: int}
        CYCLE_DETECTED:    {pattern: list[str], iteration: int}
        TOOL_CACHE_HIT:    {tool_name: str, arguments: dict}
    timestamp:
        Unix timestamp when the event was created.
    """

    type: LoopEventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Event handler protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LoopEventHandler(Protocol):
    """Protocol for objects that receive ReAct loop events.

    Implementations must be synchronous -- Rich Live rendering runs
    on the main thread and cannot await coroutines.
    """

    def on_event(self, event: LoopEvent) -> None:
        """Handle a single loop event."""
        ...


# ---------------------------------------------------------------------------
# Null implementation (default -- backward compatibility)
# ---------------------------------------------------------------------------


class NullEventHandler:
    """No-op event handler.  Used when no live display is attached."""

    def on_event(self, event: LoopEvent) -> None:
        """Silently discard the event."""
