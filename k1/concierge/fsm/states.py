"""
k1.concierge.fsm.states -- ConciergeState enum (11 FSM states).

V2 Design Ref: Section 4 (FSM States: The Definitive Table)

The FSM is the event router. It does NOT drive a loop.
It subscribes to bus topics and transitions on events.
Each state defines which actor is active and what events are expected.
"""

from __future__ import annotations

from enum import Enum, auto


class ConciergeState(Enum):
    """All 11 FSM states for the Concierge Controller.

    State-to-Event mapping (V2 Section 4, authoritative):

    | State              | Entry Trigger                          | Active Actor       |
    |--------------------|----------------------------------------|--------------------|
    | LISTENING          | response.final OR session start        | None (idle)        |
    | DISPATCHING        | user.input + Phase 1 complete           | Front LLM          |
    | COMPANIONING       | ack emitted + task dispatched          | Front (idle)       |
    | PROGRESSING        | tool.started received                  | Back LLM           |
    | DELIVERING         | task.complete received                 | Front LLM          |
    | CLARIFYING_USER    | uncertainty >= threshold               | Front LLM          |
    | CLARIFYING_WORKER  | task.suspended received                | Front LLM          |
    | CANCELLING         | task.cancel emitted by Front           | Controller         |
    | INTERRUPT_HANDLING | user.input during COMPANIONING/PROG.  | Front LLM          |
    | PROACTIVE_WAKE     | task.complete while LISTENING          | Controller         |
    | WEAVING            | pending_results non-empty after final  | Front LLM          |
    """

    LISTENING = auto()
    DISPATCHING = auto()
    COMPANIONING = auto()
    PROGRESSING = auto()
    DELIVERING = auto()
    CLARIFYING_USER = auto()
    CLARIFYING_WORKER = auto()
    CANCELLING = auto()
    INTERRUPT_HANDLING = auto()
    PROACTIVE_WAKE = auto()
    WEAVING = auto()
