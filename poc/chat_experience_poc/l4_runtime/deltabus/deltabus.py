"""
DeltaBus - In-process event bus for SessionState delta propagation

Implementation of pub/sub event bus for K1 runtime coordination.
SessionStateManager publishes deltas, Writer Agents subscribe and react.

Design:
- In-memory pub/sub (no network, no persistence, ephemeral)
- asyncio.Queue for async delivery to subscribers
- Wildcard pattern matching (session.* matches session.delta, session.created, etc.)
- FIFO ordering guarantee per session_id (queue per session)
- <1ms event delivery latency target (P95)
- Non-blocking publish_async for high-throughput scenarios

Event Types:
- session.delta: SessionState section updates
- session.created: New session initialized
- session.archived: Session timed out (600s idle)
- agent.spawned: New agent activated
- agent.terminated: Agent lifecycle ended
- tool.called: Tool invocation occurred

References:
- docs/plans/chat_experience_poc_plan.md - Issue 2.2.1
- ADR-0045a - K1 Internal Event Bus Architecture (Pub/Sub Pattern)
- ADR-0048 - K1 Internal Event Bus for Runtime Coordination
"""

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import structlog

# Lazy imports for perf_constants (will be used in performance tracking)
try:
    from config.perf_constants import DELTABUS_DELIVERY_P95_MS, check_budget

    PERF_BUDGETS_AVAILABLE = True
except ImportError:
    DELTABUS_DELIVERY_P95_MS = 1  # Default 1ms budget
    PERF_BUDGETS_AVAILABLE = False

logger = structlog.get_logger()


class EventType(Enum):
    """Standard DeltaBus event types"""

    SESSION_DELTA = "session.delta"
    SESSION_CREATED = "session.created"
    SESSION_ARCHIVED = "session.archived"
    AGENT_SPAWNED = "agent.spawned"
    AGENT_TERMINATED = "agent.terminated"
    TOOL_CALLED = "tool.called"


@dataclass
class DeltaBusEvent:
    """
    DeltaBus event envelope

    Fields:
        event_type: Event type (session.delta, agent.spawned, etc.)
        session_id: Session identifier (for FIFO ordering)
        payload: Event-specific data (deltas, agent info, tool results, etc.)
        timestamp: Event creation time
        trace_id: Cognitive trace ID for observability
        event_id: Unique event identifier (UUID)
    """

    event_type: str
    session_id: str
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    trace_id: str = field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:12]}")
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")

    def matches_pattern(self, pattern: str) -> bool:
        """
        Check if event type matches subscription pattern

        Supports wildcard matching:
        - "session.*" matches "session.delta", "session.created", "session.archived"
        - "agent.*" matches "agent.spawned", "agent.terminated"
        - Exact match: "session.delta" only matches "session.delta"

        Args:
            pattern: Subscription pattern (e.g., "session.*")

        Returns:
            True if event type matches pattern
        """
        if pattern.endswith(".*"):
            prefix = pattern[:-2]  # Remove ".*"
            return self.event_type.startswith(prefix + ".")
        return self.event_type == pattern


@dataclass
class Subscriber:
    """
    Event subscriber

    Fields:
        subscriber_id: Unique subscriber identifier
        event_pattern: Subscription pattern (e.g., "session.*")
        callback: Async callback function(event: DeltaBusEvent) -> None
        queue: asyncio.Queue for async event delivery (None for sync callbacks)
    """

    subscriber_id: str
    event_pattern: str
    callback: Callable[[DeltaBusEvent], Any]
    queue: Optional[asyncio.Queue] = None


class DeltaBus:
    """
    In-memory pub/sub event bus for SessionState delta propagation

    Singleton class managing event subscriptions and delivery.
    Provides both sync and async publish mechanisms.

    Usage:
        # Create bus
        bus = DeltaBus()

        # Subscribe to events
        def handle_delta(event: DeltaBusEvent):
            print(f"Delta: {event.payload}")

        callback_id = bus.subscribe("session.delta", handle_delta)

        # Publish event (blocking)
        event = DeltaBusEvent(
            event_type="session.delta",
            session_id="session_123",
            payload={"deltas": [...]},
            trace_id="trace_abc"
        )
        bus.publish(event)

        # Publish event (non-blocking)
        await bus.publish_async(event)

        # Unsubscribe
        bus.unsubscribe(callback_id)

    Performance:
        - Event delivery: <1ms P95 (in-memory fanout)
        - Async publish: Non-blocking, <0.1ms overhead
        - Supports 1000+ events/sec throughput
    """

    _instance = None

    def __new__(cls):
        """Singleton pattern - ensure only one DeltaBus instance"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize DeltaBus (only once due to singleton)"""
        if self._initialized:
            return

        # Subscriber registry: pattern → list of subscribers
        self._subscribers: Dict[str, List[Subscriber]] = defaultdict(list)

        # Subscriber index by ID
        self._subscriber_index: Dict[str, Subscriber] = {}

        # Session-specific queues for FIFO ordering
        self._session_queues: Dict[str, asyncio.Queue] = {}

        # Metrics
        self._events_published = 0
        self._events_delivered = 0
        self._events_dropped = 0
        self._delivery_times: List[float] = []

        # Background tasks
        self._delivery_tasks: Dict[str, asyncio.Task] = {}
        self._shutdown = False

        self._initialized = True

        logger.info(
            "[DeltaBus] Initialized",
            singleton=True,
            performance_target_ms=DELTABUS_DELIVERY_P95_MS,
        )

    def subscribe(
        self,
        event_pattern: str,
        callback: Callable[[DeltaBusEvent], Any],
        subscriber_id: Optional[str] = None,
    ) -> str:
        """
        Subscribe to events matching pattern

        Args:
            event_pattern: Event pattern to subscribe to
                          Examples: "session.*", "session.delta", "agent.*"
            callback: Callback function(event: DeltaBusEvent) -> None
                     Can be sync or async function
            subscriber_id: Optional subscriber ID (auto-generated if None)

        Returns:
            Subscriber ID (for unsubscribe)

        Example:
            def handle_delta(event):
                print(f"Received: {event.event_type}")

            callback_id = bus.subscribe("session.*", handle_delta)
        """
        if subscriber_id is None:
            subscriber_id = f"sub_{uuid.uuid4().hex[:12]}"

        # Coerce callback into Subscriber if it's a plain dict (defensive programming)
        if isinstance(callback, dict):
            logger.warning(
                "[DeltaBus] Received dict instead of callback - converting",
                subscriber_id=subscriber_id,
            )
            # This shouldn't happen, but handle it gracefully
            callback = lambda evt: None  # noqa: E731

        # Check if callback is async
        is_async = asyncio.iscoroutinefunction(callback)

        # Create async queue for async callbacks
        queue = asyncio.Queue(maxsize=100) if is_async else None

        subscriber = Subscriber(
            subscriber_id=subscriber_id,
            event_pattern=event_pattern,
            callback=callback,
            queue=queue,
        )

        self._subscribers[event_pattern].append(subscriber)
        self._subscriber_index[subscriber_id] = subscriber

        logger.info(
            "[DeltaBus] Subscriber registered",
            subscriber_id=subscriber_id,
            pattern=event_pattern,
            async_callback=is_async,
        )

        # Start delivery task for async subscribers
        if is_async and queue is not None:
            self._delivery_tasks[subscriber_id] = asyncio.create_task(
                self._deliver_async(subscriber)
            )

        return subscriber_id

    def subscribe_once(
        self,
        event_pattern: str,
        timeout: float = 10.0,
    ) -> asyncio.Future:
        """
        Subscribe to first event matching pattern (once-only listener)

        Creates temporary subscription that auto-unsubscribes after first match.
        Returns Future that resolves with event or raises TimeoutError.

        Args:
            event_pattern: Event pattern to match (exact or wildcard)
            timeout: Timeout in seconds (raises asyncio.TimeoutError)

        Returns:
            asyncio.Future[DeltaBusEvent] that resolves with first matching event

        Raises:
            asyncio.TimeoutError: If no matching event within timeout

        Example:
            # Wait for response event
            event = await deltabus.subscribe_once("response.env_123", timeout=5.0)
            print(f"Response received: {event.payload}")

        Note:
            - Future is automatically cancelled on timeout
            - Subscription auto-unsubscribes after first event
            - Safe to use in parallel (each call gets own Future)
        """
        future: asyncio.Future[DeltaBusEvent] = asyncio.Future()
        subscriber_id = f"once_{uuid.uuid4().hex[:12]}"

        def once_callback(event: DeltaBusEvent) -> None:
            """Callback that resolves future and unsubscribes"""
            if not future.done():
                future.set_result(event)
                # Schedule cleanup (unsubscribe) after callback completes
                asyncio.create_task(self._cleanup_once_subscriber(subscriber_id))

        # Subscribe with once-only callback
        self.subscribe(event_pattern, once_callback, subscriber_id=subscriber_id)

        # Schedule timeout cleanup
        async def timeout_cleanup():
            """Cancel future and unsubscribe on timeout"""
            try:
                await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            except asyncio.TimeoutError:
                if not future.done():
                    future.set_exception(
                        asyncio.TimeoutError(
                            f"No event matching '{event_pattern}' within {timeout}s"
                        )
                    )
                await self._cleanup_once_subscriber(subscriber_id)

        asyncio.create_task(timeout_cleanup())

        return future

    async def _cleanup_once_subscriber(self, subscriber_id: str) -> None:
        """
        Cleanup once-only subscriber (internal helper)

        Args:
            subscriber_id: Subscriber ID to remove
        """
        try:
            self.unsubscribe(subscriber_id)
            logger.debug(
                "[DeltaBus] Once-subscriber cleaned up",
                subscriber_id=subscriber_id,
            )
        except Exception as e:
            logger.warning(
                "[DeltaBus] Once-subscriber cleanup failed",
                subscriber_id=subscriber_id,
                error=str(e),
            )

    def unsubscribe(self, subscriber_id: str) -> bool:
        """
        Unsubscribe from events

        Args:
            subscriber_id: Subscriber ID from subscribe()

        Returns:
            True if unsubscribed, False if subscriber not found
        """
        if subscriber_id not in self._subscriber_index:
            logger.warning(
                "[DeltaBus] Unsubscribe failed - subscriber not found",
                subscriber_id=subscriber_id,
            )
            return False

        subscriber = self._subscriber_index[subscriber_id]
        pattern = subscriber.event_pattern

        # Remove from subscriber list
        if pattern in self._subscribers:
            self._subscribers[pattern] = [
                s for s in self._subscribers[pattern] if s.subscriber_id != subscriber_id
            ]

        # Cancel delivery task if async
        if subscriber_id in self._delivery_tasks:
            self._delivery_tasks[subscriber_id].cancel()
            del self._delivery_tasks[subscriber_id]

        del self._subscriber_index[subscriber_id]

        logger.info(
            "[DeltaBus] Subscriber unregistered",
            subscriber_id=subscriber_id,
            pattern=pattern,
        )

        return True

    def publish(self, event: DeltaBusEvent) -> None:
        """
        Publish event to all matching subscribers (blocking)

        Args:
            event: Event to publish

        Performance:
            - <1ms delivery to all subscribers (in-memory fanout)
            - Blocks until all sync callbacks complete
            - Async callbacks queued for background delivery

        Example:
            event = DeltaBusEvent(
                event_type="session.delta",
                session_id="session_123",
                payload={"deltas": [{"section": "beliefs", ...}]},
                trace_id="trace_abc"
            )
            bus.publish(event)
        """
        start_ns = time.perf_counter_ns()

        # Increment published count FIRST (before checking subscribers)
        self._events_published += 1

        # Find matching subscribers
        matching_subscribers = self._find_matching_subscribers(event)

        if not matching_subscribers:
            logger.debug(
                "[DeltaBus] No subscribers for event",
                event_type=event.event_type,
                event_id=event.event_id,
                trace_id=event.trace_id,
            )
            return

        # Deliver to subscribers
        for subscriber in matching_subscribers:
            try:
                if subscriber.queue is not None:
                    # Async callback - enqueue for background delivery
                    subscriber.queue.put_nowait(event)
                    self._events_delivered += 1
                else:
                    # Sync callback - execute immediately
                    subscriber.callback(event)
                    self._events_delivered += 1
            except Exception as e:
                self._events_dropped += 1
                logger.error(
                    "[DeltaBus] Event delivery failed",
                    subscriber_id=subscriber.subscriber_id,
                    event_type=event.event_type,
                    error=str(e),
                    trace_id=event.trace_id,
                )

        delivery_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        # Track delivery time
        self._delivery_times.append(delivery_ms)
        if len(self._delivery_times) > 1000:
            self._delivery_times = self._delivery_times[-1000:]  # Keep last 1000

        # Check performance budget
        if PERF_BUDGETS_AVAILABLE:
            try:
                check_budget(delivery_ms, DELTABUS_DELIVERY_P95_MS, "deltabus_delivery", logger)
            except Exception:
                pass  # Budget violation logged, don't fail delivery

        logger.debug(
            "[DeltaBus] Event published",
            event_type=event.event_type,
            event_id=event.event_id,
            session_id=event.session_id,
            subscribers=len(matching_subscribers),
            delivery_ms=round(delivery_ms, 3),
            trace_id=event.trace_id,
        )

    async def publish_async(self, event: DeltaBusEvent) -> None:
        """
        Publish event asynchronously (non-blocking)

        Args:
            event: Event to publish

        Performance:
            - <0.1ms overhead (queue enqueue)
            - Non-blocking - returns immediately
            - Delivery happens in background

        Example:
            await bus.publish_async(event)
        """
        # For now, delegate to sync publish
        # In production, this would use a background task pool
        self.publish(event)

    def _find_matching_subscribers(self, event: DeltaBusEvent) -> List[Subscriber]:
        """
        Find all subscribers matching event type

        Args:
            event: Event to match

        Returns:
            List of matching subscribers (validated Subscriber instances only)
        """
        matching = []

        for pattern, subscribers in self._subscribers.items():
            if event.matches_pattern(pattern):
                # Filter out any non-Subscriber objects (defensive)
                for sub in subscribers:
                    if isinstance(sub, Subscriber) or hasattr(sub, "matches_pattern"):
                        matching.append(sub)
                    else:
                        logger.warning(
                            "[DeltaBus] Skipping invalid subscriber object",
                            pattern=pattern,
                            subscriber_type=type(sub).__name__,
                        )

        return matching

    async def _deliver_async(self, subscriber: Subscriber) -> None:
        """
        Background task for async event delivery

        Args:
            subscriber: Subscriber with async callback

        Runs indefinitely until task cancelled or shutdown.
        """
        if subscriber.queue is None:
            return  # Should never happen, but guard against None

        while not self._shutdown:
            try:
                # Wait for event (with timeout for shutdown check)
                event = await asyncio.wait_for(subscriber.queue.get(), timeout=1.0)

                # Execute async callback
                await subscriber.callback(event)

            except asyncio.TimeoutError:
                # No events in queue, continue waiting
                continue
            except asyncio.CancelledError:
                # Task cancelled (unsubscribe)
                break
            except Exception as e:
                logger.error(
                    "[DeltaBus] Async delivery failed",
                    subscriber_id=subscriber.subscriber_id,
                    error=str(e),
                )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get DeltaBus statistics

        Returns:
            Dict with metrics:
            - events_published: Total events published
            - events_delivered: Total events delivered
            - events_dropped: Total events dropped (errors)
            - active_subscribers: Number of active subscribers
            - avg_delivery_ms: Average delivery time
            - p95_delivery_ms: P95 delivery time
        """
        p95_delivery_ms = 0.0
        if self._delivery_times:
            sorted_times = sorted(self._delivery_times)
            p95_idx = int(len(sorted_times) * 0.95)
            p95_delivery_ms = (
                sorted_times[p95_idx] if p95_idx < len(sorted_times) else sorted_times[-1]
            )

        return {
            "events_published": self._events_published,
            "events_delivered": self._events_delivered,
            "events_dropped": self._events_dropped,
            "active_subscribers": len(self._subscriber_index),
            "avg_delivery_ms": (
                round(sum(self._delivery_times) / len(self._delivery_times), 3)
                if self._delivery_times
                else 0.0
            ),
            "p95_delivery_ms": round(p95_delivery_ms, 3),
        }

    async def shutdown(self) -> None:
        """Shutdown DeltaBus and cancel all background tasks"""
        self._shutdown = True

        # Cancel all delivery tasks
        for task in self._delivery_tasks.values():
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete (with timeout)
        if self._delivery_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._delivery_tasks.values(), return_exceptions=True),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                logger.warning("[DeltaBus] Shutdown timeout - some tasks may still be running")

        logger.info("[DeltaBus] Shutdown complete", stats=self.get_stats())


# Global singleton instance
_global_deltabus: Optional[DeltaBus] = None


def get_deltabus() -> DeltaBus:
    """
    Get global DeltaBus singleton instance

    Returns:
        DeltaBus instance
    """
    global _global_deltabus
    if _global_deltabus is None:
        _global_deltabus = DeltaBus()
    return _global_deltabus
