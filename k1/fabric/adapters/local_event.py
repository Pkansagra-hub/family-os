"""
k1.fabric.adapters.local_event -- LocalEventAdapter for Fabric IEventPort (5.2.3).

In-process event dispatch with optional capture mode for testing.
Reuses the same design as SessionState's LocalEventAdapter but
targets the Fabric's ``IEventPort`` protocol (``typing.Protocol``).

Key differences from SessionState's version:
  - Returns ``SubscriptionHandle`` instead of raw ``str`` sub IDs.
  - Handler signature is ``(topic, payload)`` not ``(payload,)``.
  - Dispatch is synchronous in ``emit()`` (no background thread) for
    deterministic test behavior.  Production async dispatch is done
    by the caller or an async wrapper.

Design:
  - capture_mode: When True, stores all emitted events for later
    assertion via ``drain()``, ``get_captured()``, ``assert_emitted()``.
  - Handlers called synchronously during ``emit()`` (exception-safe).
  - Thread-safe via RLock.
  - Topic filtering: handlers only called for subscribed topics.

Usage:
  # Production-like (no capture)
  bus = LocalEventAdapter()
  handle = bus.subscribe("k1.fabric.capability.registered.v1", my_handler)
  bus.emit("k1.fabric.capability.registered.v1", {"id": "cap-1"})
  bus.unsubscribe(handle)

  # Testing (capture mode)
  bus = LocalEventAdapter(capture_mode=True)
  bus.emit("k1.fabric.pressure.warning.v1", {"level": "WARNING"})
  events = bus.drain()
  assert len(events) == 1

References:
  - IEventPort (5.1.2)
  - FAB-09 (cognitive_trace_id in payloads)
  - SessionState LocalEventAdapter pattern (k1/sessionstate/adapters/local_events.py)

Exports:
  LocalEventAdapter
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from k1.fabric.ports.event_port import SubscriptionHandle

logger = logging.getLogger(__name__)


class LocalEventAdapter:
    """
    In-process event dispatch adapter for Fabric's IEventPort.

    Implements ``IEventPort`` via structural subtyping.

    Event dispatch:
      Handlers are called synchronously in ``emit()`` for deterministic
      test behavior.  Exceptions in handlers are caught and logged.

    Capture mode:
      When ``capture_mode=True``, every ``emit()`` call stores
      ``(topic, payload, timestamp_ms)`` for later retrieval via
      ``drain()``.  Useful for test assertions.

    Thread safety:
      All methods are protected by RLock for concurrent access.
    """

    __slots__ = (
        "_handlers",
        "_subscriptions",
        "_capture_mode",
        "_captured",
        "_lock",
    )

    def __init__(self, capture_mode: bool = False) -> None:
        """
        Initialize LocalEventAdapter.

        Args:
            capture_mode: If True, store all emitted events for
                later retrieval.
        """
        # topic -> list of (sub_id, handler)
        self._handlers: Dict[str, List[Tuple[str, Callable[[str, Dict[str, Any]], None]]]] = {}
        # sub_id -> (topic, handler)
        self._subscriptions: Dict[str, Tuple[str, Callable[[str, Dict[str, Any]], None]]] = {}
        self._capture_mode = capture_mode
        self._captured: List[Tuple[str, Dict[str, Any]]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # IEventPort protocol methods
    # ------------------------------------------------------------------

    def emit(
        self,
        topic: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Emit an event to all subscribers of the given topic.

        Fire-and-forget: never raises even if handlers fail.
        Handlers called synchronously for deterministic testing.

        Args:
            topic: Event topic string.
            payload: Event payload dict.
        """
        with self._lock:
            if self._capture_mode:
                self._captured.append((topic, payload))
            handlers = list(self._handlers.get(topic, []))

        # Call handlers outside lock to avoid deadlocks
        for sub_id, handler in handlers:
            try:
                handler(topic, payload)
            except Exception as exc:
                logger.error(
                    "Handler %s failed for topic '%s': %s",
                    sub_id,
                    topic,
                    exc,
                    exc_info=True,
                )

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> SubscriptionHandle:
        """
        Subscribe a handler to events on the given topic.

        Args:
            topic: Event topic to subscribe to.
            handler: Callable ``(topic, payload) -> None``.

        Returns:
            SubscriptionHandle for later unsubscription.
        """
        with self._lock:
            sub_id = uuid.uuid4().hex[:16]
            if topic not in self._handlers:
                self._handlers[topic] = []
            self._handlers[topic].append((sub_id, handler))
            self._subscriptions[sub_id] = (topic, handler)
            return SubscriptionHandle(subscription_id=sub_id, topic=topic)

    def unsubscribe(
        self,
        handle: SubscriptionHandle,
    ) -> bool:
        """
        Remove a subscription.

        Args:
            handle: SubscriptionHandle from subscribe().

        Returns:
            True if removed, False if not found.
        """
        with self._lock:
            sub_id = handle.subscription_id
            if sub_id not in self._subscriptions:
                return False
            topic, handler = self._subscriptions.pop(sub_id)
            topic_handlers = self._handlers.get(topic, [])
            self._handlers[topic] = [(sid, h) for sid, h in topic_handlers if sid != sub_id]
            return True

    # ------------------------------------------------------------------
    # Capture mode API (testing support)
    # ------------------------------------------------------------------

    @property
    def capture_mode(self) -> bool:
        """Whether capture mode is enabled."""
        return self._capture_mode

    def enable_capture(self) -> None:
        """Enable capture mode."""
        with self._lock:
            self._capture_mode = True

    def disable_capture(self) -> None:
        """Disable capture mode (does not clear captured events)."""
        with self._lock:
            self._capture_mode = False

    def get_captured(
        self,
        topic: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Get captured events, optionally filtered by topic.

        Args:
            topic: If provided, only return events matching this topic.

        Returns:
            List of (topic, payload) tuples.
        """
        with self._lock:
            if topic is None:
                return list(self._captured)
            return [(t, p) for t, p in self._captured if t == topic]

    def drain(self) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Get and clear all captured events.

        Returns:
            List of (topic, payload) tuples.
        """
        with self._lock:
            events = list(self._captured)
            self._captured.clear()
            return events

    def assert_emitted(
        self,
        topic: str,
        count: int = 1,
    ) -> None:
        """
        Assert that an event was emitted the expected number of times.

        Args:
            topic: Topic to check.
            count: Expected emission count.

        Raises:
            AssertionError: If actual count doesn't match.
        """
        with self._lock:
            actual = sum(1 for t, _ in self._captured if t == topic)
        if actual != count:
            raise AssertionError(f"Expected {count} events on '{topic}', got {actual}")

    def clear_captured(self) -> None:
        """Clear all captured events."""
        with self._lock:
            self._captured.clear()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def subscription_count(self) -> int:
        """Total number of active subscriptions."""
        with self._lock:
            return len(self._subscriptions)

    def handler_count(self, topic: str) -> int:
        """Number of handlers for a specific topic."""
        with self._lock:
            return len(self._handlers.get(topic, []))

    @property
    def captured_count(self) -> int:
        """Number of captured events."""
        with self._lock:
            return len(self._captured)

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"LocalEventAdapter("
                f"subscriptions={len(self._subscriptions)}, "
                f"capture_mode={self._capture_mode}, "
                f"captured={len(self._captured)})"
            )
