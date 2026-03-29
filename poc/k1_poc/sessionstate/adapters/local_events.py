"""
LocalEventAdapter - In-Process Event Dispatch
===============================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.2 Define Event Port
ISSUE: 3.2.3

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Standalone operation without DeltaBus.
    In-process callback dispatch for events.
    Supports test mode with event capture.

THREAD SAFETY:
    Queue-based dispatch with consumer thread.
    Handlers called in order, in dedicated thread.

TESTING SUPPORT:
    Capture mode for test assertions.
    drain() to get emitted events.

==============================================================================
CLASS: LocalEventAdapter
==============================================================================
"""

import logging
import queue
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..ports.events import IEventPort

logger = logging.getLogger(__name__)


class LocalEventAdapter(IEventPort):
    """
    Local in-process event adapter for standalone mode.

    Dispatches events to registered handlers in-process.
    Supports capture mode for testing.

    Attributes:
        _handlers: Dict[event_type, List[handler]]
        _subscriptions: Dict[subscription_id, (event_type, handler)]
        _capture_mode: Whether to capture events for testing
        _captured_events: List of captured events
        _event_queue: Queue for async dispatch
        _dispatch_thread: Background thread for dispatch

    Example:
        adapter = LocalEventAdapter()

        # Subscribe to events
        def on_mutation(event):
            print(f"Mutation: {event}")

        sub_id = adapter.subscribe("sessionstate.mutation.approved", on_mutation)

        # Emit events
        adapter.emit("sessionstate.mutation.approved", payload)

        # For testing
        adapter.enable_capture()
        adapter.emit("sessionstate.mutation.approved", payload)
        events = adapter.get_captured_events()
    """

    def __init__(self, capture_mode: bool = False) -> None:
        """
        Initialize LocalEventAdapter.

        Args:
            capture_mode: If True, capture events for test assertions
        """
        self._handlers: Dict[str, List[Callable[[Any], None]]] = {}
        self._subscriptions: Dict[str, Tuple[str, Callable[[Any], None]]] = {}
        self._capture_mode = capture_mode
        self._captured_events: List[Tuple[str, Any, float]] = []
        self._event_queue: queue.Queue[Tuple[str, Any]] = queue.Queue()
        self._lock = threading.RLock()
        self._running = True
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop,
            daemon=True,
            name="LocalEventAdapter-Dispatch",
        )
        self._dispatch_thread.start()

        logger.info(
            "LocalEventAdapter initialized (capture_mode=%s)",
            capture_mode,
        )

    @property
    def is_connected(self) -> bool:
        """
        Always connected (local).

        Returns:
            bool: True
        """
        return True

    def emit(
        self,
        event_type: str,
        payload: Any,
    ) -> None:
        """
        Emit an event.

        Args:
            event_type: Event type string
            payload: Event payload (dataclass from events.py)

        Behavior:
            1. If capture_mode, store event
            2. Queue event for async dispatch
            3. Return immediately (fire-and-forget)
        """
        if self._capture_mode:
            with self._lock:
                self._captured_events.append((event_type, payload, time.time()))
        self._event_queue.put((event_type, payload))

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Any], None],
    ) -> str:
        """
        Subscribe to an event type.

        Args:
            event_type: Event type to subscribe to
            handler: Callback function

        Returns:
            str: Subscription ID
        """
        with self._lock:
            sub_id = str(uuid.uuid4())
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)
            self._subscriptions[sub_id] = (event_type, handler)
            return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from an event.

        Args:
            subscription_id: ID from subscribe()

        Returns:
            bool: True if found and removed
        """
        with self._lock:
            if subscription_id in self._subscriptions:
                event_type, handler = self._subscriptions.pop(subscription_id)
                if event_type in self._handlers:
                    try:
                        self._handlers[event_type].remove(handler)
                    except ValueError:
                        pass  # Handler already removed
                return True
            return False

    def _dispatch_loop(self) -> None:
        """
        Background dispatch loop.

        Runs in dedicated thread, dispatches events to handlers.
        """
        while self._running:
            try:
                event_type, payload = self._event_queue.get(timeout=0.1)
                with self._lock:
                    handlers = list(self._handlers.get(event_type, []))
                for handler in handlers:
                    try:
                        handler(payload)
                    except Exception as e:
                        logger.error(
                            f"Handler error for {event_type}: {e}",
                            exc_info=True,
                        )
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Dispatch loop error: {e}", exc_info=True)

    # =========================================================================
    # TESTING SUPPORT
    # =========================================================================

    def enable_capture(self) -> None:
        """
        Enable capture mode for testing.

        Events will be stored in _captured_events.
        """
        self._capture_mode = True

    def disable_capture(self) -> None:
        """
        Disable capture mode.
        """
        self._capture_mode = False

    def get_captured_events(
        self,
        event_type: Optional[str] = None,
    ) -> List[Tuple[str, Any, float]]:
        """
        Get captured events.

        Args:
            event_type: Optional filter by type

        Returns:
            List of (event_type, payload, timestamp) tuples
        """
        with self._lock:
            if event_type is None:
                return list(self._captured_events)
            return [
                (et, payload, ts) for et, payload, ts in self._captured_events if et == event_type
            ]

    def drain(self) -> List[Tuple[str, Any, float]]:
        """
        Get and clear all captured events.

        Returns:
            List of captured events

        Clears the capture buffer after returning.
        """
        with self._lock:
            events = list(self._captured_events)
            self._captured_events.clear()
            return events

    def assert_emitted(
        self,
        event_type: str,
        count: int = 1,
    ) -> None:
        """
        Assert that event was emitted expected number of times.

        Args:
            event_type: Event type to check
            count: Expected count

        Raises:
            AssertionError: If count doesn't match
        """
        with self._lock:
            actual = sum(1 for et, _, _ in self._captured_events if et == event_type)
            if actual != count:
                raise AssertionError(
                    f"Expected {count} events of type '{event_type}', got {actual}"
                )

    def clear_captured(self) -> None:
        """
        Clear captured events.
        """
        with self._lock:
            self._captured_events.clear()

    def stop(self) -> None:
        """
        Stop the dispatch thread.

        Call on shutdown.
        """
        self._running = False
        if self._dispatch_thread.is_alive():
            self._dispatch_thread.join(timeout=1.0)

    def wait_for_dispatch(self, timeout: float = 1.0) -> bool:
        """
        Wait for event queue to be empty.

        Args:
            timeout: Max time to wait in seconds

        Returns:
            bool: True if queue is empty, False if timeout
        """
        start = time.time()
        while not self._event_queue.empty():
            if time.time() - start > timeout:
                return False
            time.sleep(0.01)
        return True

    def get_subscription_count(self) -> int:
        """
        Get number of active subscriptions.

        Returns:
            int: Number of subscriptions
        """
        with self._lock:
            return len(self._subscriptions)

    def get_handler_count(self, event_type: str) -> int:
        """
        Get number of handlers for event type.

        Args:
            event_type: Event type to check

        Returns:
            int: Number of handlers
        """
        with self._lock:
            return len(self._handlers.get(event_type, []))

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"LocalEventAdapter("
            f"subscriptions={len(self._subscriptions)}, "
            f"capture_mode={self._capture_mode}, "
            f"captured={len(self._captured_events)})"
        )


# =============================================================================
# IMPLEMENTATION NOTES
# =============================================================================
"""
1. THREAD SAFETY:
   - Use queue.Queue for thread-safe dispatch
   - Handlers called in dedicated thread
   - Never call handlers in emit() thread

2. ERROR ISOLATION:
   - If handler raises, log and continue
   - Don't let one handler break others

3. TESTING PATTERN:
   adapter = LocalEventAdapter(capture_mode=True)

   # Do operations that emit events
   manager.mutate("beliefs", "append", data)

   # Assert events
   adapter.assert_emitted("sessionstate.mutation.approved", 1)
   events = adapter.drain()
   assert events[0][1].section == "beliefs"

4. CLEANUP:
   Call stop() on shutdown to terminate dispatch thread.
   Daemon thread will auto-stop when main thread exits.

5. PERFORMANCE:
   emit() is non-blocking (just queues).
   Dispatch happens async in background thread.
"""
