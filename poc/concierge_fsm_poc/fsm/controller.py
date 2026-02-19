"""Concierge FSM Controller -- Epic 1.1 (FSM-001, FSM-002, FSM-003).

Pure-logic FSM with zero I/O.  Deterministic table lookup.
All 8 states, 14 events, 15 actions, 14 transition types (18 table entries).
Aligned to ``k1/concierge/concierge_fsm_flows.md`` Parts 1-3.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# FSM-001: State / Event / Action enums
# ---------------------------------------------------------------------------


class State(str, Enum):
    """8 concierge FSM states (flows file Part 1)."""

    LISTENING = "LISTENING"
    ACKING = "ACKING"
    CLARIFYING = "CLARIFYING"
    DISPATCHING = "DISPATCHING"
    COMPANIONING = "COMPANIONING"
    PROGRESSING = "PROGRESSING"
    DELIVERING = "DELIVERING"
    INTERRUPT_HANDLING = "INTERRUPT_HANDLING"


class Event(str, Enum):
    """14 FSM events (flows file Part 2)."""

    # Phase 1 outcomes
    MESSAGE_RECEIVED = "message_received"
    PHASE1_COMPLETE = "phase1_complete"
    GAPS_DETECTED = "gaps_detected"
    CRISIS_DETECTED = "crisis_detected"

    # Clarification
    CLARIFICATION_RECEIVED = "clarification_received"
    MAX_ROUNDS_REACHED = "max_rounds_reached"

    # Dispatch + Execution
    DISPATCH_STARTED = "dispatch_started"
    PRELIMINARY_ACK_SENT = "preliminary_ack_sent"
    PROGRESS_RECEIVED = "progress_received"
    DISPATCH_COMPLETE = "dispatch_complete"

    # Delivery
    RESPONSE_DELIVERED = "response_delivered"
    TURN_COMPLETE = "turn_complete"

    # Interrupt
    INTERRUPT_DETECTED = "interrupt_detected"
    INTERRUPT_HANDLED = "interrupt_handled"


class Action(str, Enum):
    """15 FSM actions emitted on transitions."""

    ACQUIRE_LOCK = "acquire_lock"
    RUN_PHASE1 = "run_phase1"
    ROUTE_BY_TIER = "route_by_tier"
    CRISIS_RESPONSE = "crisis_response"
    SEND_CLARIFICATION = "send_clarification"
    MERGE_CLARIFICATION = "merge_clarification"
    FORCE_PROCEED = "force_proceed"
    START_TOOL_LOOP = "start_tool_loop"
    SEND_ACKNOWLEDGE = "send_acknowledge"
    STREAM_PROGRESS = "stream_progress"
    ASSEMBLE_RESPONSE = "assemble_response"
    FLUSH_AND_CHECKPOINT = "flush_and_checkpoint"
    CANCEL_INFLIGHT = "cancel_inflight"
    PARTIAL_FLUSH = "partial_flush"
    REENTER_ACKING = "reenter_acking"


# ---------------------------------------------------------------------------
# FSM-003: Error types
# ---------------------------------------------------------------------------


class InvalidTransitionError(Exception):
    """Raised when no transition exists for (state, event)."""

    def __init__(self, state: State, event: Event) -> None:
        self.state = state
        self.event = event
        super().__init__(f"No transition from {state.value} on {event.value}")


class ErrorSeverity(str, Enum):
    """Error severity classification (Section 5.5)."""

    RECOVERABLE = "recoverable"
    DEGRADED = "degraded"
    TERMINAL = "terminal"


# ---------------------------------------------------------------------------
# FSM-002: FSMController with TRANSITION_TABLE
# ---------------------------------------------------------------------------


class FSMController:
    """Deterministic FSM controller -- pure table lookup, zero I/O.

    18 table entries covering 14 transition types from
    ``concierge_fsm_flows.md`` Part 3.
    """

    INTERRUPTIBLE: frozenset[State] = frozenset(
        {
            State.DISPATCHING,
            State.COMPANIONING,
            State.PROGRESSING,
            State.CLARIFYING,
        }
    )

    TRANSITION_TABLE: Dict[Tuple[State, Event], Tuple[State, List[Action]]] = {
        # T1: New message arrives
        (State.LISTENING, Event.MESSAGE_RECEIVED): (
            State.ACKING,
            [Action.ACQUIRE_LOCK, Action.RUN_PHASE1],
        ),
        # T2: Crisis detected in Phase 1 (bypass all dispatch)
        (State.ACKING, Event.CRISIS_DETECTED): (
            State.DELIVERING,
            [Action.CRISIS_RESPONSE],
        ),
        # T3: Phase 1 complete, no gaps -> dispatch
        (State.ACKING, Event.PHASE1_COMPLETE): (
            State.DISPATCHING,
            [Action.ROUTE_BY_TIER],
        ),
        # T4: Phase 1 found gaps -> clarify (rounds < 3)
        (State.ACKING, Event.GAPS_DETECTED): (
            State.CLARIFYING,
            [Action.SEND_CLARIFICATION],
        ),
        # T5: User answered clarification -> re-enter ACKING
        (State.CLARIFYING, Event.CLARIFICATION_RECEIVED): (
            State.ACKING,
            [Action.MERGE_CLARIFICATION],
        ),
        # T6: 3 rounds exhausted -> force-proceed to DISPATCHING
        (State.CLARIFYING, Event.MAX_ROUNDS_REACHED): (
            State.DISPATCHING,
            [Action.FORCE_PROCEED, Action.ROUTE_BY_TIER],
        ),
        # T7: Ack sent -> enter companion phase (MEDIUM/HIGH tier)
        (State.DISPATCHING, Event.PRELIMINARY_ACK_SENT): (
            State.COMPANIONING,
            [Action.SEND_ACKNOWLEDGE, Action.START_TOOL_LOOP],
        ),
        # T8: Dispatch done immediately -> deliver (LOW tier, no companion)
        (State.DISPATCHING, Event.DISPATCH_COMPLETE): (
            State.DELIVERING,
            [Action.ASSEMBLE_RESPONSE],
        ),
        # T9: Progress update during companion phase
        (State.COMPANIONING, Event.PROGRESS_RECEIVED): (
            State.PROGRESSING,
            [Action.STREAM_PROGRESS],
        ),
        # T10: Orchestrator/tool done while still in companion
        (State.COMPANIONING, Event.DISPATCH_COMPLETE): (
            State.DELIVERING,
            [Action.ASSEMBLE_RESPONSE],
        ),
        # T11: All work done after progress phase
        (State.PROGRESSING, Event.DISPATCH_COMPLETE): (
            State.DELIVERING,
            [Action.ASSEMBLE_RESPONSE],
        ),
        # T12: Response shown -> return to LISTENING
        (State.DELIVERING, Event.RESPONSE_DELIVERED): (
            State.LISTENING,
            [Action.FLUSH_AND_CHECKPOINT],
        ),
        # T13a-d: Interrupt from any interruptible state
        (State.DISPATCHING, Event.INTERRUPT_DETECTED): (
            State.INTERRUPT_HANDLING,
            [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH],
        ),
        (State.COMPANIONING, Event.INTERRUPT_DETECTED): (
            State.INTERRUPT_HANDLING,
            [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH],
        ),
        (State.PROGRESSING, Event.INTERRUPT_DETECTED): (
            State.INTERRUPT_HANDLING,
            [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH],
        ),
        (State.CLARIFYING, Event.INTERRUPT_DETECTED): (
            State.INTERRUPT_HANDLING,
            [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH],
        ),
        # T14: Interrupt processed -> re-enter ACKING
        (State.INTERRUPT_HANDLING, Event.INTERRUPT_HANDLED): (
            State.ACKING,
            [Action.REENTER_ACKING],
        ),
    }

    def __init__(self) -> None:
        self._state: State = State.LISTENING
        self._history: list[tuple[State, Event, State]] = []

    @property
    def state(self) -> State:
        """Current FSM state."""
        return self._state

    @property
    def history(self) -> list[tuple[State, Event, State]]:
        """Copy of transition history [(from, event, to), ...]."""
        return list(self._history)

    def is_interruptible(self) -> bool:
        """Whether the current state accepts INTERRUPT_DETECTED."""
        return self._state in self.INTERRUPTIBLE

    def transition(self, event: Event) -> tuple[State, list[Action]]:
        """Execute a state transition.

        Returns:
            (new_state, actions) on success.

        Raises:
            InvalidTransitionError: when no transition exists for (state, event).
        """
        key = (self._state, event)
        if key not in self.TRANSITION_TABLE:
            raise InvalidTransitionError(self._state, event)
        new_state, actions = self.TRANSITION_TABLE[key]
        self._history.append((self._state, event, new_state))
        self._state = new_state
        return new_state, actions

    def reset(self) -> None:
        """Reset FSM to LISTENING with empty history."""
        self._state = State.LISTENING
        self._history.clear()
