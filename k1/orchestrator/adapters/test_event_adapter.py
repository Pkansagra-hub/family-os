"""
k1.orchestrator.adapters.test_event_adapter -- TestEventAdapter (6.1.14).

Test adapter for IEventSubscriptionPort.

Design:
  - In-memory subscription registry with wildcard matching.
  - emit() dispatches to all matching handlers synchronously.
  - fire() is an alias for emit() -- explicit test name.
  - All emitted events captured for assertion.
  - Handlers are sync: Callable[[str, Dict], None].

Wildcard matching:
  - ``k1.capability.*`` matches ``k1.capability.completed.v1``
  - Wildcard must be trailing ``*`` after a dot prefix.

References:
  - Issue 6.1.14 in orchestrator-implementation-plan.md
  - k1/orchestrator/ports/event_subscription_port.py (IEventSubscriptionPort)
  - k1/fabric/ports/event_port.py (SubscriptionHandle)

Exports:
  TestEventAdapter
"""

from __future__ import annotations

import fnmatch
import uuid
from typing import Any, Callable, Dict, List, Tuple

from k1.fabric.ports.event_port import SubscriptionHandle

# ---------------------------------------------------------------------------
# 6.1.14 -- TestEventAdapter
# ---------------------------------------------------------------------------


class TestEventAdapter:
    """
    Test IEventSubscriptionPort adapter with wildcard matching.

    Subscriptions stored in-memory. emit()/fire() dispatch to all
    matching handlers synchronously. All emitted events logged.
    """

    def __init__(self) -> None:
        self.subscriptions: Dict[str, List[Callable]] = {}
        self._handle_map: Dict[str, Tuple[str, Callable]] = {}
        self.emitted: List[Tuple[str, Dict[str, Any]]] = []

    # ------------------------------------------------------------------
    # IEventSubscriptionPort.subscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> SubscriptionHandle:
        """Register handler for topic (supports wildcards)."""
        handle = SubscriptionHandle(
            subscription_id=str(uuid.uuid4()),
            topic=topic,
        )
        self.subscriptions.setdefault(topic, []).append(handler)
        self._handle_map[handle.subscription_id] = (topic, handler)
        return handle

    # ------------------------------------------------------------------
    # IEventSubscriptionPort.unsubscribe
    # ------------------------------------------------------------------

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """Remove a subscription. Returns True if found."""
        entry = self._handle_map.pop(handle.subscription_id, None)
        if entry is None:
            return False
        topic, handler = entry
        handlers = self.subscriptions.get(topic, [])
        if handler in handlers:
            handlers.remove(handler)
            if not handlers:
                del self.subscriptions[topic]
        return True

    # ------------------------------------------------------------------
    # IEventSubscriptionPort.emit
    # ------------------------------------------------------------------

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        """Emit event: log and dispatch to matching handlers."""
        self.emitted.append((topic, payload))
        self._dispatch(topic, payload)

    # ------------------------------------------------------------------
    # Dispatch (with wildcard matching)
    # ------------------------------------------------------------------

    def _dispatch(self, topic: str, payload: Dict[str, Any]) -> None:
        """Dispatch to handlers matching topic (exact or wildcard)."""
        for pattern, handlers in self.subscriptions.items():
            if pattern == topic or fnmatch.fnmatch(topic, pattern):
                for handler in list(handlers):
                    handler(topic, payload)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def fire(self, topic: str, payload: Dict[str, Any]) -> None:
        """Alias for emit() -- explicit test name for simulating events."""
        self.emit(topic, payload)

    def assert_subscribed(self, topic: str) -> None:
        """Assert that at least one handler is subscribed to *topic*."""
        assert topic in self.subscriptions and self.subscriptions[topic], (
            f"Expected subscription for topic '{topic}', " f"got {list(self.subscriptions.keys())}"
        )

    def assert_emitted(self, topic: str, count: int = 1) -> None:
        """Assert that *topic* was emitted exactly *count* times."""
        actual = sum(1 for t, _ in self.emitted if t == topic)
        assert actual == count, f"Expected topic '{topic}' emitted {count} time(s), got {actual}"

    def get_emitted(self, topic: str) -> List[Dict[str, Any]]:
        """Return all payloads emitted for *topic*."""
        return [payload for t, payload in self.emitted if t == topic]

    def reset(self) -> None:
        """Clear emitted log (subscriptions preserved)."""
        self.emitted.clear()
