"""FSM controller -- pure-logic state machine, zero I/O."""

from .controller import Action, ErrorSeverity, Event, FSMController, InvalidTransitionError, State

__all__ = [
    "Action",
    "ErrorSeverity",
    "Event",
    "FSMController",
    "InvalidTransitionError",
    "State",
]
