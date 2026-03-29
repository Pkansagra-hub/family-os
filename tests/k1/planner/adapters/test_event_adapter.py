"""TestEventAdapter -- in-memory IEventPort implementation (SS16.2.7).

Implements the IEventPort Protocol (SS15.8) with:
- Synchronous emit() that captures and dispatches to registered handlers
- subscribe()/unsubscribe() for handler management
- inject_event() helper for simulating inbound events (HIL responses)
- Rich assertion helpers for topic filtering and publish capture
- Protocol-structural compliance with IEventPort

File location: tests/k1/planner/adapters/ (SS30.3)
Never importable from production code.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Tuple

from k1.fabric.ports.event_port import SubscriptionHandle


class TestEventAdapter:
    """In-memory IEventPort for deterministic testing (SS16.2.7).

    Constructor takes no arguments. Internal state tracks all published
    events and all subscriptions for handler dispatch.

    Internal state
    --------------
    _publish_capture : List[Tuple[str, Any]]
        Ordered (topic, payload) pairs for all emitted events.
    _subscriptions : Dict[str, List[Tuple[str, Callable]]]
        topic -> list of (subscription_id, handler) tuples.
    _subscription_handles : List[SubscriptionHandle]
        All handles ever issued (for debugging).
    """

    def __init__(self) -> None:
        self._publish_capture: List[Tuple[str, Any]] = []
        self._subscriptions: Dict[str, List[Tuple[str, Callable[[str, Any], None]]]] = {}
        self._subscription_handles: List[SubscriptionHandle] = []

    # ------------------------------------------------------------------
    # IEventPort Protocol methods
    # ------------------------------------------------------------------

    def emit(self, topic: str, payload: Any) -> None:
        """Emit event: capture and invoke registered handlers.

        Synchronous, never raises. If a handler raises, the exception
        is caught and swallowed (matching production contract).
        """
        self._publish_capture.append((topic, payload))

        # Invoke all handlers registered for this topic
        for _sub_id, handler in self._subscriptions.get(topic, []):
            try:
                handler(topic, payload)
            except Exception:
                pass  # Handlers must not raise; swallow if they do

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Any], None],
    ) -> SubscriptionHandle:
        """Register handler for topic, return SubscriptionHandle."""
        sub_id = str(uuid.uuid4())
        handle = SubscriptionHandle(subscription_id=sub_id, topic=topic)

        if topic not in self._subscriptions:
            self._subscriptions[topic] = []
        self._subscriptions[topic].append((sub_id, handler))
        self._subscription_handles.append(handle)

        return handle

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """Remove a subscription. Returns True if found and removed."""
        topic = handle.topic
        sub_id = handle.subscription_id

        if topic not in self._subscriptions:
            return False

        original_len = len(self._subscriptions[topic])
        self._subscriptions[topic] = [
            (sid, h) for sid, h in self._subscriptions[topic] if sid != sub_id
        ]
        return len(self._subscriptions[topic]) < original_len

    # ------------------------------------------------------------------
    # Test helper: inject inbound events
    # ------------------------------------------------------------------

    def inject_event(self, topic: str, payload: Any) -> None:
        """Simulate inbound event by calling registered handlers directly.

        Does NOT add to _publish_capture (this simulates receiving, not
        emitting). Use for HIL responses, external triggers, etc.
        """
        for _sub_id, handler in self._subscriptions.get(topic, []):
            try:
                handler(topic, payload)
            except Exception:
                pass  # Swallow handler exceptions

    # ------------------------------------------------------------------
    # Assertion / introspection helpers
    # ------------------------------------------------------------------

    def get_published(self, topic: str) -> List[Any]:
        """Return all payloads published to the given topic."""
        return [payload for t, payload in self._publish_capture if t == topic]

    def get_all_published(self) -> List[Tuple[str, Any]]:
        """Return all (topic, payload) pairs in emission order."""
        return list(self._publish_capture)

    def get_published_topics(self) -> List[str]:
        """Return unique topics that were published (in first-seen order)."""
        seen: List[str] = []
        for t, _ in self._publish_capture:
            if t not in seen:
                seen.append(t)
        return seen

    @property
    def publish_count(self) -> int:
        """Total number of emitted events."""
        return len(self._publish_capture)

    def assert_published_count(self, topic: str, n: int) -> None:
        """Assert exactly n events were published to the topic."""
        actual = len(self.get_published(topic))
        assert actual == n, f"Expected {n} events on topic '{topic}', got {actual}"

    def assert_topic_emitted(self, topic: str) -> None:
        """Assert at least one event was published to the topic."""
        found = self.get_published(topic)
        assert len(found) > 0, (
            f"No events published to topic '{topic}' "
            f"(published topics: {self.get_published_topics()})"
        )

    def assert_topic_not_emitted(self, topic: str) -> None:
        """Assert no events were published to the topic."""
        found = self.get_published(topic)
        assert len(found) == 0, f"Expected no events on topic '{topic}', found {len(found)}"

    @property
    def subscription_count(self) -> int:
        """Total number of active subscriptions."""
        return sum(len(subs) for subs in self._subscriptions.values())

    def has_subscription(self, topic: str) -> bool:
        """Check if any handler is subscribed to the topic."""
        return len(self._subscriptions.get(topic, [])) > 0

    def clear(self) -> None:
        """Reset all capture state. Does not remove subscriptions."""
        self._publish_capture.clear()
