"""Plan state machine [F04].

Enum-based FSM tracking plan lifecycle.  11 states, monotonic transitions.

Contains:
 - PlanState enum (11 members)
 - TRANSITION_TABLE constant (23 unique edges, SS18.4)
 - IllegalStateTransitionError (PlannerError subclass)
 - PlanStateMachine (thin validation wrapper around _current_state)

PlanState lives here (not in types.py) because PlanStateMachine uses it
directly.

Design decisions
----------------
- PlanState is ``(str, Enum)`` for JSON serialisation compatibility.
- Terminal states: COMPLETED, FAILED, CANCELLED.
- Micro-replan states: MICRO_SKETCH, MICRO_EXPAND, MICRO_VALIDATE.
- COMMITTING is reused for micro-replan Stage 4.
- TRANSITION_TABLE maps each source state to its frozenset of legal targets.
- PlanStateMachine is a pure state container with validation logic.
  It does NOT do I/O, hold port references, or emit deltas directly.
  Delta emission is the CALLER's responsibility via the on_transition callback.
- force_failed() and force_cancelled() bypass TRANSITION_TABLE for error handling.

Import graph (Layer 0)
----------------------
k1.planner.plan_fsm
  -> stdlib (enum, typing)
  -> k1.planner.types (PlannerError)

NEVER import from any service, port, or adapter module.

References
----------
- planner.md Section 18.1 (State Catalog)
- planner.md Section 18.2-18.4 (State Diagrams, Transition Table)
- planner.md Section 18.5 (Terminal States)
- planner.md Section 18.9 (FSM Invariant Enforcement)
- planner.md Section 30.5.1 F04
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Dict, FrozenSet, Optional

from k1.planner.types import PlannerError


class PlanState(str, Enum):
    """Plan lifecycle states (Section 18.1).

    10 states covering full planning pipeline, micro-replan pipeline,
    and terminal outcomes.

    Transient states (active pipeline):
        IDLE        -- Initial and resting state.  No plan in progress.
        SKETCHING   -- Stage 1 active (discovery tools + LLM sketch).
        EXPANDING   -- Stage 2 active (tool mapping + LLM expand).
        VALIDATING  -- Stage 3 active (deterministic checks + LLM arbiter + HIL).
        COMMITTING  -- Stage 4 active (plan assembly + WAL persist + event emit).

    Micro-replan states (abbreviated pipeline):
        MICRO_SKETCH   -- Micro-replan Stage 1 (re-sketch remaining steps).
        MICRO_EXPAND   -- Micro-replan Stage 2 (re-map tools for replacements).
        MICRO_VALIDATE -- Micro-replan Stage 3 (validate replacement steps).
        (COMMITTING is reused for micro-replan Stage 4.)

    Terminal states (plan outcome resolved):
        COMPLETED  -- Plan successfully committed and delivered.
        FAILED     -- Plan failed at any stage (unrecoverable after retry).
        CANCELLED  -- Plan cancelled by Orchestrator via send_cancel().
    """

    IDLE = "IDLE"
    SKETCHING = "SKETCHING"
    EXPANDING = "EXPANDING"
    VALIDATING = "VALIDATING"
    COMMITTING = "COMMITTING"
    MICRO_SKETCH = "MICRO_SKETCH"
    MICRO_EXPAND = "MICRO_EXPAND"
    MICRO_VALIDATE = "MICRO_VALIDATE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        """True if the plan outcome is resolved (no further transitions)."""
        return self in _TERMINAL_STATES

    @property
    def is_micro(self) -> bool:
        """True if this is a micro-replan stage."""
        return self in _MICRO_STATES

    @property
    def is_active(self) -> bool:
        """True if a plan is actively being processed (not IDLE, not terminal)."""
        return self != PlanState.IDLE and not self.is_terminal


# Pre-computed sets for property checks (avoid repeated set creation)
_TERMINAL_STATES = frozenset({PlanState.COMPLETED, PlanState.FAILED, PlanState.CANCELLED})
_MICRO_STATES = frozenset(
    {PlanState.MICRO_SKETCH, PlanState.MICRO_EXPAND, PlanState.MICRO_VALIDATE}
)


# ---------------------------------------------------------------------------
# Section 18.4 -- Transition table (23 unique edges)
# ---------------------------------------------------------------------------

TRANSITION_TABLE: Dict[PlanState, FrozenSet[PlanState]] = {
    # Full pipeline (7 edges)
    PlanState.IDLE: frozenset({PlanState.SKETCHING, PlanState.MICRO_SKETCH}),
    PlanState.SKETCHING: frozenset({PlanState.EXPANDING, PlanState.FAILED, PlanState.CANCELLED}),
    PlanState.EXPANDING: frozenset({PlanState.VALIDATING, PlanState.FAILED, PlanState.CANCELLED}),
    PlanState.VALIDATING: frozenset(
        {
            PlanState.COMMITTING,
            PlanState.EXPANDING,  # revise loop (guarded by revise_count < 1)
            PlanState.FAILED,
            PlanState.CANCELLED,
        }
    ),
    PlanState.COMMITTING: frozenset({PlanState.COMPLETED, PlanState.CANCELLED}),
    # Terminal reset (3 edges)
    PlanState.COMPLETED: frozenset({PlanState.IDLE}),
    PlanState.FAILED: frozenset({PlanState.IDLE}),
    PlanState.CANCELLED: frozenset({PlanState.IDLE}),
    # Micro-replan (4 new edges; COMMITTING->COMPLETED reused)
    PlanState.MICRO_SKETCH: frozenset({PlanState.MICRO_EXPAND, PlanState.FAILED}),
    PlanState.MICRO_EXPAND: frozenset({PlanState.MICRO_VALIDATE, PlanState.FAILED}),
    PlanState.MICRO_VALIDATE: frozenset({PlanState.COMMITTING, PlanState.FAILED}),
}


# ---------------------------------------------------------------------------
# Section 30.5.1 F04 -- IllegalStateTransitionError
# ---------------------------------------------------------------------------


class IllegalStateTransitionError(PlannerError):
    """Raised when an illegal FSM transition is attempted.

    Propagates to PipelineController's PLAN-12 handler which catches it
    and routes to FAILED via ``force_failed()``.

    Attributes
    ----------
    from_state : PlanState
        State the FSM was in when the illegal transition was attempted.
    to_state : PlanState
        Target state that was rejected.
    trigger : str
        Optional description of what caused the transition attempt.
    """

    def __init__(
        self,
        from_state: PlanState,
        to_state: PlanState,
        trigger: str = "",
    ) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.trigger = trigger
        msg = f"Illegal state transition: {from_state.value} -> {to_state.value}"
        if trigger:
            msg += f" (trigger: {trigger})"
        super().__init__(msg, stage=from_state.value)


# ---------------------------------------------------------------------------
# Section 30.5.1 F04 -- PlanStateMachine
# ---------------------------------------------------------------------------


class PlanStateMachine:
    """Thin FSM validation wrapper around PlanState (Section 18, 30.5.1 F04).

    Pure state container with transition validation.  Does NOT do I/O,
    does NOT hold port references, does NOT emit deltas directly.
    Delta emission is the CALLER's responsibility via the ``on_transition``
    callback.

    Parameters
    ----------
    on_transition : optional callback
        ``Callable[[PlanState, PlanState, str], None]`` invoked AFTER
        ``_current_state`` is updated, with ``(from_state, to_state, trigger)``.
        PipelineController provides this for delta/log emission.
        The callback MUST NOT raise -- PipelineController wraps it in
        try/except to prevent delta emission failures from blocking
        pipeline execution.
    """

    __slots__ = ("_current_state", "_on_transition")

    def __init__(
        self,
        on_transition: Optional[Callable[[PlanState, PlanState, str], None]] = None,
    ) -> None:
        self._current_state: PlanState = PlanState.IDLE
        self._on_transition = on_transition

    @property
    def current_state(self) -> PlanState:
        """Current FSM state."""
        return self._current_state

    # -- 2.1.3: transition validation --

    def transition(self, new_state: PlanState, trigger: str = "") -> PlanState:
        """Validate and apply a state transition.

        Checks that ``(current_state, new_state)`` is in
        :data:`TRANSITION_TABLE`.  If legal, updates ``_current_state``
        and invokes the ``on_transition`` callback (if set) AFTER the
        state update so the observer sees the new state.

        Parameters
        ----------
        new_state : PlanState
            Target state.
        trigger : str
            Description of what caused the transition (for logging/deltas).

        Returns
        -------
        PlanState
            The new current state (same as *new_state*).

        Raises
        ------
        IllegalStateTransitionError
            If the transition is not in TRANSITION_TABLE.
        """
        old_state = self._current_state
        legal_targets = TRANSITION_TABLE.get(old_state)
        if legal_targets is None or new_state not in legal_targets:
            raise IllegalStateTransitionError(old_state, new_state, trigger)
        self._current_state = new_state
        if self._on_transition is not None:
            self._on_transition(old_state, new_state, trigger)
        return new_state

    # -- 2.1.3: reset --

    def reset(self) -> None:
        """Reset FSM to IDLE.  Only legal from terminal states.

        Does NOT invoke ``on_transition`` callback -- PipelineController
        emits a separate ``plan_end`` delta for terminal -> IDLE
        transitions (Section 18.6, PLAN_END lifecycle phase).

        Raises
        ------
        IllegalStateTransitionError
            If the current state is not terminal.
        """
        if self._current_state not in _TERMINAL_STATES:
            raise IllegalStateTransitionError(self._current_state, PlanState.IDLE, "reset")
        self._current_state = PlanState.IDLE

    # -- 2.1.5: force transitions (bypass TRANSITION_TABLE) --

    def force_failed(self, trigger: str = "") -> PlanState:
        """Force transition to FAILED from any active state.

        Bypasses TRANSITION_TABLE -- used by PipelineController's
        PLAN-12 handler for uncaught exceptions and explicit error
        routing.

        Parameters
        ----------
        trigger : str
            Description of the failure cause.

        Returns
        -------
        PlanState
            ``PlanState.FAILED``.

        Raises
        ------
        IllegalStateTransitionError
            If called from IDLE, COMPLETED, FAILED, or CANCELLED
            (cannot fail a non-active plan).
        """
        if not self._current_state.is_active:
            raise IllegalStateTransitionError(self._current_state, PlanState.FAILED, trigger)
        old_state = self._current_state
        self._current_state = PlanState.FAILED
        if self._on_transition is not None:
            self._on_transition(old_state, PlanState.FAILED, trigger)
        return PlanState.FAILED

    def force_cancelled(self, trigger: str = "") -> PlanState:
        """Force transition to CANCELLED from any active state.

        Bypasses TRANSITION_TABLE -- used for cooperative cancellation
        from any active state.

        Parameters
        ----------
        trigger : str
            Description of the cancellation cause.

        Returns
        -------
        PlanState
            ``PlanState.CANCELLED``.

        Raises
        ------
        IllegalStateTransitionError
            If called from IDLE, COMPLETED, FAILED, or CANCELLED
            (cannot cancel a non-active plan).
        """
        if not self._current_state.is_active:
            raise IllegalStateTransitionError(self._current_state, PlanState.CANCELLED, trigger)
        old_state = self._current_state
        self._current_state = PlanState.CANCELLED
        if self._on_transition is not None:
            self._on_transition(old_state, PlanState.CANCELLED, trigger)
        return PlanState.CANCELLED


__all__ = [
    "PlanState",
    "TRANSITION_TABLE",
    "IllegalStateTransitionError",
    "PlanStateMachine",
]
