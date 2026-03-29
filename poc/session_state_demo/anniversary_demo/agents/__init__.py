"""
Sub-Agent System
================

Provides specialized agents that can be spawned by the Concierge:
- SearchAgent: Searches accommodations, restaurants, activities (READ-ONLY)
- BookingAgent: Makes reservations and bookings (READ-ONLY, confirms with Concierge)

All sub-agents have READ-ONLY access to SessionState.
Only the Concierge has WRITE access.
"""

from poc.session_state_demo.anniversary_demo.agents.base import (
    AgentResult,
    AgentStatus,
    BaseSubAgent,
    ReadOnlyBridge,
)
from poc.session_state_demo.anniversary_demo.agents.booking_agent import BookingAgent
from poc.session_state_demo.anniversary_demo.agents.search_agent import SearchAgent

__all__ = [
    "AgentResult",
    "AgentStatus",
    "BaseSubAgent",
    "ReadOnlyBridge",
    "SearchAgent",
    "BookingAgent",
]
