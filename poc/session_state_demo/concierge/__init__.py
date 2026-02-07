"""
Concierge FSM Module
====================

Simplified Concierge state machine for the session state demo.
Demonstrates L1 cognitive architecture patterns:
- FSM-based conversation flow
- Intent classification
- Gap detection + clarification
- Complexity-based routing

Reference: k1_cognitive_architecture_skeleton.mmd L1_CONCIERGE
"""

from poc.session_state_demo.concierge.fsm import ConciergeFSM, FSMEvent, FSMObserver
from poc.session_state_demo.concierge.states import (
    ClassificationResult,
    ComplexityTier,
    ConciergeState,
    TurnResult,
)

__all__ = [
    "ConciergeFSM",
    "ConciergeState",
    "ComplexityTier",
    "ClassificationResult",
    "TurnResult",
    "FSMEvent",
    "FSMObserver",
]
