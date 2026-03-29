"""
IEventPort - Event Bus Interface
=================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.2 Define Event Port
ISSUE: 3.2.1

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Define the interface SessionState EXPECTS from event bus.
    Allows SessionState to emit events without knowing about DeltaBus.

IMPLEMENTATIONS:
    - LocalEventAdapter: In-process callbacks (standalone mode)
    - DeltaBusAdapter: K1 DeltaBus integration (future)

EVENT TYPES (from events.py):
    - sessionstate.mutation.requested
    - sessionstate.mutation.approved
    - sessionstate.mutation.rejected
    - sessionstate.eviction.triggered
    - sessionstate.eviction.completed
    - sessionstate.emergency.activated
    - sessionstate.emergency.resolved
    - sessionstate.reconstruction.started

==============================================================================
INTERFACE: IEventPort
==============================================================================
"""

from abc import ABC, abstractmethod
from typing import Any, Callable


class IEventPort(ABC):
    """
    Interface for SessionState event emission.

    SessionState uses this port to:
    - Emit events for mutations, evictions, emergencies
    - Allow other components to subscribe to SessionState events

    Properties:
        is_connected: Whether event bus is available

    Example:
        class LocalEventAdapter(IEventPort):
            def emit(self, event_type: str, payload: Any) -> None:
                # Dispatch to local handlers
                for handler in self._handlers.get(event_type, []):
                    handler(payload)
    """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if event bus is connected.

        Returns:
            bool: True if events can be emitted

        Notes:
            - LocalEventAdapter: Always True
            - DeltaBusAdapter: May be False if disconnected
        """
        pass

    @abstractmethod
    def emit(
        self,
        event_type: str,
        payload: Any,
    ) -> None:
        """
        Emit an event.

        Args:
            event_type: Event type from EventType enum
                        (e.g., 'sessionstate.mutation.approved')
            payload: Event payload dataclass (from events.py)

        Behavior:
            - Fire-and-forget (non-blocking)
            - If not connected, log warning and drop event
            - Never raise exceptions

        Event types:
            See k1/sessionstate/events.py for all types
        """
        pass

    @abstractmethod
    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Any], None],
    ) -> str:
        """
        Subscribe to an event type.

        Args:
            event_type: Event type to subscribe to
            handler: Callback function to invoke

        Returns:
            str: Subscription ID (for unsubscribe)

        Handler signature:
            def handler(payload: EventPayload) -> None

        Example:
            def on_mutation_approved(payload: MutationApprovedEvent):
                print(f"Mutation approved: {payload.section}")

            sub_id = event_port.subscribe(
                "sessionstate.mutation.approved",
                on_mutation_approved,
            )
        """
        pass

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from an event.

        Args:
            subscription_id: ID returned from subscribe()

        Returns:
            bool: True if unsubscribed, False if not found
        """
        pass

    def emit_batch(
        self,
        events: list[tuple[str, Any]],
    ) -> None:
        """
        Emit multiple events in batch.

        Default implementation calls emit() for each.
        Implementations may override for efficiency.

        Args:
            events: List of (event_type, payload) tuples
        """
        for event_type, payload in events:
            self.emit(event_type, payload)


# =============================================================================
# IMPLEMENTATION NOTES
# =============================================================================
"""
1. FIRE-AND-FORGET:
   emit() should never block.
   Use queue for async dispatch if needed.

2. ERROR ISOLATION:
   If handler raises, log and continue.
   Don't let one handler break others.

3. THREAD SAFETY:
   Implementations must be thread-safe.
   Use locks or queues for handler dispatch.

4. TESTING SUPPORT:
   LocalEventAdapter should support:
   - drain(): Get all emitted events
   - get_events(type): Get events of specific type
   - clear(): Clear captured events

   This enables test assertions:
   assert len(adapter.get_events("mutation.approved")) == 1

5. IMPLEMENTATIONS TO CREATE:
   - LocalEventAdapter (k1/sessionstate/adapters/local_events.py)
   - DeltaBusAdapter (k1/bus/adapters/sessionstate.py) - FUTURE

6. EVENT FORMAT:
   - event_type is string (e.g., "sessionstate.mutation.approved")
   - payload is dataclass from events.py
   - Serialization handled by adapter
"""
