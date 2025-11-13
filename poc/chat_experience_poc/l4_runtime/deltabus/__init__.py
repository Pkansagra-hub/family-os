"""
DeltaBus - In-process event bus for SessionState delta propagation

This module implements an in-memory pub/sub system for K1 runtime coordination.
DeltaBus enables SessionStateManager to publish deltas, and Writer Agents to subscribe
and react. This decouples state changes from persistence logic.

Key Features:
- In-memory pub/sub (no network, no persistence)
- Event types: session.delta, session.created, session.archived, agent.*, tool.*
- Wildcard subscriptions: session.* matches all session events
- FIFO ordering guarantee per session_id
- <1ms event delivery latency (P95)
- Non-blocking async publish

References:
- docs/plans/chat_experience_poc_plan.md - Issue 2.2.1
- ADR-0045a - K1 Internal Event Bus Architecture
- ADR-0048 - K1 Internal Event Bus for Runtime Coordination
"""

from .deltabus import DeltaBus, DeltaBusEvent, EventType, Subscriber, get_deltabus

__all__ = ["DeltaBus", "DeltaBusEvent", "Subscriber", "EventType", "get_deltabus"]
