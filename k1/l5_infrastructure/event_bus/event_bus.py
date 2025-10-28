"""
Event Bus - Core Pub/Sub System for Cross-Layer Communication

Layer: L5 Infrastructure
Component: Event Bus
Priority: P0 (Critical Path)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0004a: Layer 1-2 Event Bus Communication Pattern
      * Pub/sub pattern for Layer 1 → Layer 5 → Layer 2 communication
      * Async delivery (<5ms P95 event propagation, non-blocking)
      * Zero-copy event passing (shared buffer, no serialization overhead)
      * Hot path optimized: L1 → L5 (emit) → L2 (subscribe) <10ms total
      * Section: "Component 1: Event Bus (Layer 5 Infrastructure)"
      * Performance: Publish <2ms P95 (L1 → L5), Delivery <5ms P95 (L5 → L2)

    - ADR-0004b: Module Dependency Management & Import Linting
      * Layer 5 (Infrastructure) cannot import ANY other layers
      * Foundation layer - all layers can import Layer 5
      * Section: "Layer 5 (Infrastructure)"

Dependencies:
    Internal:
        - k1.l5_infrastructure.event_bus.schemas.Event (event payload schemas)
        - k1.l5_infrastructure.event_bus.schemas.EventTopic (topic definitions)

    External:
        - asyncio (async runtime, queue management)
        - time (timestamp generation)
        - collections.defaultdict (subscriber registry)
        - typing (type hints)

Connects To:
    Upstream (Publishers):
        - k1.l1_input.audio_input (audio events)
        - k1.l1_input.voice_intent (intent detection events)
        - k1.l1_input.stream_switch (modality switching events)
        - k1.l1_input.gesture_input (gesture events)

    Downstream (Subscribers):
        - k1.l2_orchestration.orchestrator (intent routing, orchestration trigger)
        - k1.l2_orchestration.planner (plan generation trigger)
        - k1.l3_execution.agent_fabric (agent event notifications)
        - Custom subscribers (extensibility)

Performance Budgets:
    - Publish latency: <2ms P95 (L1 → L5, enqueue only)
    - Delivery latency: <5ms P95 (L5 → L2, end-to-end)
    - Total end-to-end: <10ms P95 (L1 → L2 via L5)
    - Topic filtering: <1ms P95 (dict lookup)
    - Queue capacity: 1000 events max (prevents unbounded growth)
    - Memory overhead: <5MB total (<1MB ring buffer + <10KB per subscriber)
    - Event bus CPU: <1% overhead
    - Throughput: ~5000 events/sec delivery capacity (typical load: 10-20 events/sec)

Observability:
    - Metrics:
        * k1_event_bus_published_total{topic} (counter: events published)
        * k1_event_bus_delivered_total{topic, status} (counter: delivery success/timeout/error)
        * k1_event_bus_queue_depth{topic} (gauge: current queue depth, target <10)
        * k1_event_bus_subscribers{topic} (gauge: active subscriber count)
        * k1_event_bus_delivery_latency_ms{topic} (histogram: P50/P95/P99)
        * k1_event_bus_publish_latency_ms{topic} (histogram: P50/P95/P99)

    - Traces:
        * Span: event_bus.publish (attributes: topic, event_id, subscriber_count, cognitive_trace_id)
        * Span: event_bus.deliver_to_subscriber (child of publish, per subscriber)

    - Logs:
        * INFO: event published (topic, event_id, subscriber_count, cognitive_trace_id)
        * WARNING: subscriber timeout (topic, subscriber_id, timeout_ms)
        * WARNING: queue overflow (topic, dropped_count)
        * WARNING: event_no_subscribers (topic, session_id, trace_id)
        * ERROR: delivery failed (topic, subscriber_id, error)

References:
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd (Layer 1-2-5 flow)
    - ADR-0004a: Event Bus Communication Pattern (primary design document)
    - Research: Enterprise Integration Patterns (Hohpe & Woolf 2003) - Pub/Sub pattern
    - Research: Actor Model (Hewitt 1973) - Message-passing foundation
    - Test: tests/k1/l5_infrastructure/event_bus/test_event_bus.py
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Third-party imports
# None required for core event bus

# Internal imports
# NOTE: Layer 5 (Infrastructure) cannot import other K1 layers per ADR-0004b
# Event schemas should be in same package: k1.l5_infrastructure.event_bus.schemas

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@infrastructure-team): Load from k1/config/event_bus.yml (ADR-0004a)
# Assigned to: Issue #L5-2.1.1
DEFAULT_CONFIG = {
    "max_queue_size": 1000,  # Ring buffer capacity (prevents unbounded growth)
    "delivery_timeout_ms": 5000,  # 5s per subscriber callback timeout
    "queue_overflow_strategy": "drop_oldest",  # Drop oldest events on overflow
    "max_subscribers_per_topic": 100,
    "max_topics": 50,
    "max_concurrent_deliveries": 1000,
    "enable_metrics": True,
    "enable_tracing": True,
}


# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class EventTopic(Enum):
    """
    Event topics for cross-layer communication (Layer 1 → Layer 2 via Layer 5)

    ADR-0004a: Section "Event Schema Definitions"
    """

    # Intent & Commands
    INTENT_DETECTED = (
        "intent.detected"  # User intent classification (3-tier: regex/SLM/LLM)
    )
    USER_INPUT = "user.input"  # Raw user message/action
    VOICE_COMMAND = "voice.command"  # Voice-based command (speech recognition)

    # Audio Events
    AUDIO_STARTED = "audio.started"  # Audio stream began
    AUDIO_ENDED = "audio.ended"  # Audio stream ended
    BARGE_IN = "audio.barge_in"  # User interruption

    # System Events
    CONSOLIDATION_COMPLETE = "system.consolidation_complete"  # K0 consolidation done
    SESSION_ENDED = "system.session_ended"  # Session termination
    QUOTA_EXCEEDED = "system.quota_exceeded"  # Usage quota hit


@dataclass
class Event:
    """
    Event envelope for all event bus messages

    ADR-0004a: Section "Component 1: Event Bus"

    Fields:
        topic: Event topic (routing key)
        session_id: Session identifier (for correlation)
        payload: Event-specific data (dict, flexible schema)
        cognitive_trace_id: Trace ID for observability (propagated end-to-end)
        timestamp: Unix timestamp (when event created)
    """

    topic: EventTopic
    session_id: str
    payload: Dict[str, Any]
    cognitive_trace_id: str
    timestamp: float


@dataclass
class SubscriberMetadata:
    """
    Subscriber registration metadata

    Fields:
        subscriber_id: Unique subscriber identifier
        topic: Topic subscribed to
        callback: Async callback function
        registered_at: Unix timestamp (when registered)
        events_delivered: Total events delivered to subscriber
        last_delivery_latency_ms: Most recent delivery latency
        status: "healthy" | "slow" | "failed"
    """

    subscriber_id: str
    topic: EventTopic
    callback: Callable[[Event], Awaitable[None]]
    registered_at: float
    events_delivered: int = 0
    last_delivery_latency_ms: float = 0.0
    status: str = "healthy"  # "healthy" | "slow" | "failed"


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class EventBus:
    """
    Event Bus: Core pub/sub system for cross-layer communication

    Purpose:
        Enable Layer 1 (Input) to publish events to Layer 2 (Orchestration)
        without violating layering rules (Layer 1 cannot import Layer 2).

        Solution: Layer 1 → Layer 5 (EventBus) → Layer 2 via pub/sub pattern.

    Architecture:
        Publisher (L1) → EventBus (L5) → Ring Buffer (1000 capacity)
                                       → Topic Filter (dict lookup)
                                       → Async Delivery Queue
                                       → Subscribers (L2, L3, custom)

    Responsibilities:
        1. Manage subscriber registrations per topic (subscribe/unsubscribe)
        2. Publish events to topics (async, non-blocking)
        3. Maintain zero-copy ring buffer (1000 events max)
        4. Deliver events to subscribers (async, parallel)
        5. Enforce FIFO ordering per topic
        6. Track event delivery status (success/timeout/error)
        7. Provide admin operations (flush, stats, monitoring)
        8. Propagate cognitive_trace_id for observability

    Performance Budget (from ADR-0004a):
        - Publish latency: <2ms P95 (L1 → L5, enqueue only)
        - Delivery latency: <5ms P95 (L5 → L2, end-to-end)
        - Total: <10ms P95 (L1 → L2 via L5)
        - Queue capacity: 1000 events
        - Delivery throughput: ~5000 events/sec
        - Typical load: 10-20 events/sec (well below capacity)

    Ring Buffer Implementation:
        - Type: asyncio.Queue(maxsize=1000)
        - Overflow strategy: Drop oldest events (not newest)
        - Thread-safe: Yes (asyncio)
        - Memory: ~1MB (1000 × 1KB avg event)

    Subscriber Delivery:
        - Strategy: Fire-and-forget (non-blocking)
        - Timeout: 5s per subscriber callback
        - On timeout: Log WARNING, remove slow subscriber
        - Retry: No (drop and move to next)
        - Parallel delivery: asyncio.gather (all subscribers)

    Topic Filtering:
        - Dictionary: {topic → [subscribers]}
        - Lookup time: O(1)
        - Wildcard topics: Future enhancement (ADR-0004b)

    Error Handling:
        - Bad topic: Raise ValueError
        - Bad callback: Raise TypeError
        - Delivery timeout: Log WARNING, mark subscriber "slow"
        - Queue overflow: Drop oldest events, emit metric

    ADR-0004a: Section "Component 1: Event Bus (Layer 5 Infrastructure)"
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize event bus

        Args:
            config: Optional configuration dict (defaults to DEFAULT_CONFIG)

        Raises:
            ValueError: If config invalid

        TODO(@infrastructure-team): Initialize event bus components
        Assigned to: Issue #L5-2.1.1
        """
        self.config = config or DEFAULT_CONFIG

        # Subscriber registry: {topic → [SubscriberMetadata]}
        self.subscribers: Dict[EventTopic, List[SubscriberMetadata]] = defaultdict(list)

        # Event queue (ring buffer): asyncio.Queue with bounded capacity
        max_queue_size = self.config["max_queue_size"]
        self.event_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)

        # Delivery task (background loop)
        self._delivery_task: Optional[asyncio.Task] = None

        # Stats (for monitoring)
        self._stats = {
            "events_published_total": 0,
            "events_delivered_total": 0,
            "events_dropped_total": 0,
            "queue_overflow_count": 0,
        }

        # Lifecycle state
        self._running = False

        logger.info(
            "event_bus_initialized",
            max_queue_size=max_queue_size,
            max_subscribers_per_topic=self.config["max_subscribers_per_topic"],
        )

    async def subscribe(
        self,
        topic: EventTopic,
        callback: Callable[[Event], Awaitable[None]],
        subscriber_id: str,
    ) -> None:
        """
        Subscribe to topic events

        Registers async callback to receive events for specified topic.
        Callback will be invoked asynchronously when events published.

        Args:
            topic: Event topic to subscribe to
            callback: Async function called on event (must be non-blocking)
            subscriber_id: Unique subscriber identifier

        Raises:
            ValueError: If callback not async or subscriber_id invalid
            RuntimeError: If max subscribers per topic exceeded

        Performance:
            - Registration overhead: <1ms

        Usage:
            # Layer 2 subscribes to Layer 1 events
            async def handle_intent(event: Event):
                intent = event.payload["intent"]
                await orchestrator.handle_intent(intent, event.session_id)

            await event_bus.subscribe(
                EventTopic.INTENT_DETECTED,
                handle_intent,
                subscriber_id="orchestrator_main",
            )

        ADR-0004a: Section "Component 1: Event Bus"

        TODO(@infrastructure-team): Implement subscription management
        Assigned to: Issue #L5-2.1.1

        Steps:
            1. Validate callback is async (inspect.iscoroutinefunction)
            2. Validate subscriber_id not already registered for topic
            3. Check max_subscribers_per_topic limit
            4. Store (topic, callback, subscriber_id) in subscribers dict
            5. Create SubscriberMetadata record
            6. Emit metric: k1_event_bus_subscribers{topic} (gauge)
            7. Log: INFO subscriber_registered
        """
        # TODO(@infrastructure-team): Validate callback is async
        if not asyncio.iscoroutinefunction(callback):
            raise TypeError(f"Callback must be async function, got {type(callback)}")

        # TODO(@infrastructure-team): Validate subscriber_id
        if not subscriber_id:
            raise ValueError("subscriber_id cannot be empty")

        # TODO(@infrastructure-team): Check max subscribers per topic
        max_subs = self.config["max_subscribers_per_topic"]
        if len(self.subscribers[topic]) >= max_subs:
            raise RuntimeError(f"Max subscribers per topic exceeded: {max_subs}")

        # TODO(@infrastructure-team): Check duplicate subscriber_id for topic
        for sub in self.subscribers[topic]:
            if sub.subscriber_id == subscriber_id:
                raise ValueError(
                    f"Subscriber {subscriber_id} already registered for topic {topic}"
                )

        # TODO(@infrastructure-team): Create subscriber metadata
        metadata = SubscriberMetadata(
            subscriber_id=subscriber_id,
            topic=topic,
            callback=callback,
            registered_at=time.time(),
        )

        # TODO(@infrastructure-team): Add to subscriber registry
        self.subscribers[topic].append(metadata)

        # TODO(@infrastructure-team): Emit metric
        logger.info(
            "subscriber_registered",
            topic=topic.value,
            subscriber_id=subscriber_id,
            total_subscribers=len(self.subscribers[topic]),
        )

    async def publish(
        self,
        topic: EventTopic,
        event: Event,
        cognitive_trace_id: Optional[str] = None,
    ) -> None:
        """
        Publish event to topic (async, non-blocking)

        Adds event to ring buffer for async delivery to all subscribers.
        Returns immediately (fire-and-forget, <2ms P95).

        Args:
            topic: Topic to publish to
            event: Event object with payload
            cognitive_trace_id: Optional trace ID for observability

        Raises:
            ValueError: If topic invalid
            RuntimeError: If event bus not running

        Performance:
            - Publish latency: <2ms P95 (enqueue only, non-blocking)
            - Delivery latency: <5ms P95 (to all subscribers, async)
            - Total: <10ms P95 end-to-end (L1 → L2)

        Observability:
            - Metric: k1_event_bus_published_total{topic} (counter)
            - Metric: k1_event_bus_publish_latency_ms{topic} (histogram)
            - Trace: Span event_bus.publish (attributes: topic, event_id, subscriber_count, cognitive_trace_id)
            - Log: INFO event published (topic, event_id, subscriber_count)

        Usage:
            # Layer 1 publishes intent detection event
            event = Event(
                topic=EventTopic.INTENT_DETECTED,
                session_id="session_123",
                payload={
                    "intent": "weather_query",
                    "confidence": 0.95,
                    "tier": 2,  # SLM classified
                },
                cognitive_trace_id="trace_456",
                timestamp=time.time(),
            )
            await event_bus.publish(EventTopic.INTENT_DETECTED, event)

        ADR-0004a: Section "Component 1: Event Bus"

        TODO(@infrastructure-team): Implement publish logic
        Assigned to: Issue #L5-2.1.1

        Steps:
            1. Validate topic and event
            2. Check event bus is running
            3. Update event.cognitive_trace_id if provided
            4. Create trace span with cognitive_trace_id
            5. Try to add event to ring buffer (queue.put_nowait)
            6. If queue full (QueueFull exception):
               - Drop oldest event (queue.get_nowait + queue.put_nowait)
               - Increment queue_overflow_count
               - Emit metric: k1_event_bus_queue_overflow_total{topic}
               - Log: WARNING queue_overflow
            7. Increment events_published_total
            8. Record publish latency metric
            9. Return immediately (fire-and-forget)
        """
        start_time = time.time()

        # TODO(@infrastructure-team): Validate topic
        if not isinstance(topic, EventTopic):
            raise ValueError(f"Invalid topic type: {type(topic)}")

        # TODO(@infrastructure-team): Validate event
        if not isinstance(event, Event):
            raise ValueError(f"Invalid event type: {type(event)}")

        # TODO(@infrastructure-team): Check running state
        if not self._running:
            raise RuntimeError("Event bus not running. Call start() first.")

        # TODO(@infrastructure-team): Update cognitive_trace_id if provided
        if cognitive_trace_id:
            event.cognitive_trace_id = cognitive_trace_id

        # TODO(@infrastructure-team): Create trace span
        # from k1.l5_infrastructure.observability import create_span
        # with create_span("event_bus.publish", cognitive_trace_id=event.cognitive_trace_id) as span:
        #     span.set_attributes(topic=topic.value, session_id=event.session_id)

        # TODO(@infrastructure-team): Add to queue (non-blocking)
        try:
            self.event_queue.put_nowait(event)
        except asyncio.QueueFull:
            # TODO(@infrastructure-team): Drop oldest event
            try:
                dropped_event = self.event_queue.get_nowait()
                self.event_queue.put_nowait(event)
                self._stats["queue_overflow_count"] += 1
                self._stats["events_dropped_total"] += 1

                logger.warning(
                    "queue_overflow",
                    topic=topic.value,
                    dropped_event_session_id=dropped_event.session_id,
                    dropped_event_topic=dropped_event.topic.value,
                )
            except Exception as e:
                logger.error("queue_overflow_handling_failed", error=str(e))
                raise

        # TODO(@infrastructure-team): Update stats
        self._stats["events_published_total"] += 1

        # TODO(@infrastructure-team): Emit metrics
        publish_latency_ms = (time.time() - start_time) * 1000

        logger.info(
            "event_published",
            topic=topic.value,
            session_id=event.session_id,
            cognitive_trace_id=event.cognitive_trace_id,
            subscriber_count=len(self.subscribers.get(topic, [])),
            publish_latency_ms=publish_latency_ms,
        )

    async def unsubscribe(
        self,
        topic: EventTopic,
        subscriber_id: str,
    ) -> None:
        """
        Unsubscribe from topic

        Removes subscriber registration for specified topic.

        Args:
            topic: Topic to unsubscribe from
            subscriber_id: Subscriber identifier

        Performance:
            - Unregister overhead: <1ms

        ADR-0004a: Section "Component 1: Event Bus"

        TODO(@infrastructure-team): Implement unsubscription
        Assigned to: Issue #L5-2.1.1

        Steps:
            1. Find subscriber in subscribers[topic] list
            2. Remove from list
            3. Emit metric: k1_event_bus_subscribers{topic} (gauge)
            4. Log: INFO subscriber_unregistered
        """
        # TODO(@infrastructure-team): Find and remove subscriber
        subscribers_for_topic = self.subscribers.get(topic, [])
        for i, sub in enumerate(subscribers_for_topic):
            if sub.subscriber_id == subscriber_id:
                del subscribers_for_topic[i]
                logger.info(
                    "subscriber_unregistered",
                    topic=topic.value,
                    subscriber_id=subscriber_id,
                    remaining_subscribers=len(subscribers_for_topic),
                )
                return

        # Subscriber not found (not an error, just log)
        logger.warning(
            "subscriber_not_found",
            topic=topic.value,
            subscriber_id=subscriber_id,
        )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get event bus statistics (for monitoring)

        Returns:
            Dict with:
                - topics_active: Number of topics with subscribers
                - subscribers_total: Total subscriber count across all topics
                - events_published_total: Lifetime events published
                - events_delivered_total: Lifetime events delivered
                - events_dropped_total: Lifetime events dropped (queue overflow)
                - queue_depth: Current queue depth
                - queue_overflow_count: Total queue overflow events
                - delivery_latencies: {topic: p95_ms}

        Performance:
            - Stats collection: <5ms

        Observability:
            - Metrics: k1_event_bus_queue_depth{topic}, k1_event_bus_subscribers{topic}

        ADR-0004a: Section "Component 1: Event Bus"

        TODO(@infrastructure-team): Implement stats collection
        Assigned to: Issue #L5-2.1.1
        """
        # TODO(@infrastructure-team): Collect stats from subscribers and queue
        topics_with_subscribers = [
            topic for topic, subs in self.subscribers.items() if len(subs) > 0
        ]
        subscribers_total = sum(len(subs) for subs in self.subscribers.values())

        stats = {
            "topics_active": len(topics_with_subscribers),
            "subscribers_total": subscribers_total,
            "events_published_total": self._stats["events_published_total"],
            "events_delivered_total": self._stats["events_delivered_total"],
            "events_dropped_total": self._stats["events_dropped_total"],
            "queue_depth": self.event_queue.qsize(),
            "queue_overflow_count": self._stats["queue_overflow_count"],
            "running": self._running,
        }

        return stats

    async def _delivery_loop(self):
        """
        Background task: Deliver events to subscribers

        Runs continuously, consuming events from ring buffer and
        delivering to all subscribers for that topic in parallel.

        Performance:
            - Delivery latency: <5ms P95 (per event to all subscribers)
            - Timeout: 5s per subscriber callback
            - Parallel delivery: asyncio.gather

        Error Handling:
            - Subscriber timeout: Log WARNING, mark subscriber "slow"
            - Subscriber exception: Log ERROR, mark subscriber "failed"
            - No subscribers: Log WARNING (event published but no listeners)

        ADR-0004a: Section "Component 1: Event Bus - _delivery_loop"

        TODO(@infrastructure-team): Implement delivery loop
        Assigned to: Issue #L5-2.1.1

        Steps:
            1. Loop: while self._running
            2. Get event from queue (await queue.get())
            3. Get subscribers for event.topic
            4. If no subscribers:
               - Log: WARNING event_no_subscribers
               - Continue to next event
            5. Deliver to all subscribers in parallel:
               - Create tasks: [asyncio.wait_for(sub.callback(event), timeout=5) for sub in subscribers]
               - Run: await asyncio.gather(*tasks, return_exceptions=True)
            6. For each result:
               - If success: Update subscriber.events_delivered, subscriber.status = "healthy"
               - If timeout: Log WARNING, mark subscriber.status = "slow"
               - If exception: Log ERROR, mark subscriber.status = "failed"
            7. Update events_delivered_total
            8. Emit metric: k1_event_bus_delivery_latency_ms{topic}
            9. Emit metric: k1_event_bus_delivered_total{topic, status}
        """
        logger.info("delivery_loop_started")

        while self._running:
            try:
                # TODO(@infrastructure-team): Get event from queue (blocking)
                event = await self.event_queue.get()

                # TODO(@infrastructure-team): Get subscribers for topic
                subscribers_for_topic = self.subscribers.get(event.topic, [])

                if not subscribers_for_topic:
                    # TODO(@infrastructure-team): Log warning (no subscribers)
                    logger.warning(
                        "event_no_subscribers",
                        topic=event.topic.value,
                        session_id=event.session_id,
                        trace_id=event.cognitive_trace_id,
                    )
                    continue

                # TODO(@infrastructure-team): Deliver to all subscribers (parallel)
                start_time = time.time()

                # Create delivery tasks with timeout
                timeout_s = self.config["delivery_timeout_ms"] / 1000
                tasks = [
                    asyncio.wait_for(sub.callback(event), timeout=timeout_s)
                    for sub in subscribers_for_topic
                ]

                # Execute in parallel (gather with return_exceptions=True)
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # TODO(@infrastructure-team): Process results
                for i, (sub, result) in enumerate(zip(subscribers_for_topic, results)):
                    if isinstance(result, asyncio.TimeoutError):
                        # Timeout: mark subscriber slow
                        sub.status = "slow"
                        logger.warning(
                            "subscriber_timeout",
                            topic=event.topic.value,
                            subscriber_id=sub.subscriber_id,
                            timeout_ms=timeout_s * 1000,
                        )
                    elif isinstance(result, Exception):
                        # Exception: mark subscriber failed
                        sub.status = "failed"
                        logger.error(
                            "delivery_failed",
                            topic=event.topic.value,
                            subscriber_id=sub.subscriber_id,
                            error=str(result),
                        )
                    else:
                        # Success: update stats
                        sub.events_delivered += 1
                        sub.status = "healthy"

                # TODO(@infrastructure-team): Update stats and metrics
                delivery_latency_ms = (time.time() - start_time) * 1000
                self._stats["events_delivered_total"] += 1

                logger.info(
                    "event_delivered",
                    topic=event.topic.value,
                    session_id=event.session_id,
                    subscriber_count=len(subscribers_for_topic),
                    delivery_latency_ms=delivery_latency_ms,
                    cognitive_trace_id=event.cognitive_trace_id,
                )

            except asyncio.CancelledError:
                logger.info("delivery_loop_cancelled")
                break
            except Exception as e:
                logger.error("delivery_loop_error", error=str(e))
                # Continue loop (don't crash on errors)

    async def start(self):
        """
        Start event bus delivery loop

        Starts background task to deliver events to subscribers.
        Must be called before publishing events.

        ADR-0004a: Section "Component 1: Event Bus"

        TODO(@infrastructure-team): Start delivery loop
        Assigned to: Issue #L5-2.1.1
        """
        if self._running:
            logger.warning("event_bus_already_running")
            return

        self._running = True
        self._delivery_task = asyncio.create_task(self._delivery_loop())
        logger.info("event_bus_started")

    async def shutdown(self) -> None:
        """
        Graceful shutdown - stop accepting events and flush queues

        Guarantees:
            - In-flight events delivered (up to 10s timeout)
            - All queues flushed
            - Subscribers notified (if applicable)

        ADR-0004a: Section "Component 1: Event Bus"

        TODO(@infrastructure-team): Implement graceful shutdown
        Assigned to: Issue #L5-2.1.1

        Steps:
            1. Set self._running = False (stop accepting new events)
            2. Wait for queue to drain (up to 10s timeout)
            3. Cancel delivery task
            4. Wait for delivery task to finish
            5. Log: INFO event_bus_shutdown
        """
        logger.info("event_bus_shutdown_starting")

        # TODO(@infrastructure-team): Stop accepting new events
        self._running = False

        # TODO(@infrastructure-team): Wait for queue to drain (10s timeout)
        shutdown_timeout = 10.0
        start_time = time.time()

        while (
            not self.event_queue.empty()
            and (time.time() - start_time) < shutdown_timeout
        ):
            await asyncio.sleep(0.1)

        # TODO(@infrastructure-team): Cancel delivery task
        if self._delivery_task:
            self._delivery_task.cancel()
            try:
                await self._delivery_task
            except asyncio.CancelledError:
                pass

        logger.info(
            "event_bus_shutdown_complete",
            events_published_total=self._stats["events_published_total"],
            events_delivered_total=self._stats["events_delivered_total"],
            events_dropped_total=self._stats["events_dropped_total"],
        )


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================


def create_event(
    topic: EventTopic,
    session_id: str,
    payload: Dict[str, Any],
    cognitive_trace_id: str,
) -> Event:
    """
    Helper: Create event with current timestamp

    Args:
        topic: Event topic
        session_id: Session identifier
        payload: Event-specific data
        cognitive_trace_id: Trace ID for observability

    Returns:
        Event object ready for publishing

    Usage:
        event = create_event(
            EventTopic.INTENT_DETECTED,
            session_id="session_123",
            payload={"intent": "weather_query", "confidence": 0.95},
            cognitive_trace_id="trace_456",
        )
        await event_bus.publish(event.topic, event)

    TODO(@infrastructure-team): Implement event creation helper
    Assigned to: Issue #L5-2.1.1
    """
    return Event(
        topic=topic,
        session_id=session_id,
        payload=payload,
        cognitive_trace_id=cognitive_trace_id,
        timestamp=time.time(),
    )


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "EventBus",
    "Event",
    "EventTopic",
    "SubscriberMetadata",
    "create_event",
]

# Global event bus instance (singleton pattern)
# NOTE: Modules should import this instance, not create new EventBus instances
# Usage: from k1.l5_infrastructure.event_bus.event_bus import event_bus
event_bus = EventBus()


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_event_bus_published_total{topic} (counter: events published)
#   - k1_event_bus_delivered_total{topic, status} (counter: delivery success/timeout/error)
#   - k1_event_bus_queue_depth{topic} (gauge: current queue depth, target <10)
#   - k1_event_bus_subscribers{topic} (gauge: active subscriber count)
#   - k1_event_bus_delivery_latency_ms{topic} (histogram: P50/P95/P99)
#   - k1_event_bus_publish_latency_ms{topic} (histogram: P50/P95/P99)
#   - k1_event_bus_queue_overflow_total{topic} (counter: queue overflow events)
#
# Traces to generate:
#   - Span name: event_bus.publish
#   - Attributes: topic, event_id, subscriber_count, cognitive_trace_id
#   - Child spans: event_bus.deliver_to_subscriber (per subscriber)
#   - Links to: upstream component spans (Layer 1 intent router, etc.)
#
# Logs to emit:
#   - Level: INFO (normal events), WARNING (timeout/overflow), ERROR (failures)
#   - Fields: component="event_bus", method, topic, session_id, cognitive_trace_id, status, latency_ms
#   - Events: event_published, event_delivered, subscriber_registered, subscriber_timeout, queue_overflow
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# All async methods must:
#   1. Accept cognitive_trace_id parameter (or extract from Event)
#   2. Create trace span with this ID
#   3. Pass ID to downstream components (subscribers)
#   4. Include ID in all log statements
#
# This enables end-to-end request tracing across K1 layers (L1 → L5 → L2).
#
# Example:
#   # Layer 1 publishes event with trace_id
#   event = Event(..., cognitive_trace_id="trace_123")
#   await event_bus.publish(event.topic, event)
#
#   # Layer 2 receives event with same trace_id
#   async def handle_intent(event: Event):
#       logger.info("intent_received", trace_id=event.cognitive_trace_id)
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/event_bus/test_event_bus.py
#   - Test: publish/subscribe basic flow (single subscriber)
#   - Test: publish/subscribe multiple subscribers (parallel delivery)
#   - Test: subscriber timeout handling (mark "slow")
#   - Test: subscriber exception handling (mark "failed")
#   - Test: queue overflow (drop oldest events)
#   - Test: no subscribers (warning logged)
#   - Test: cognitive_trace_id propagation
#   - Test: graceful shutdown (flush queue)
#   - Test: performance budgets (<2ms publish, <5ms delivery, <10ms end-to-end)
#
# No simulation code allowed:
#   - No asyncio.sleep() for testing timeouts (use real components)
#   - Use WARD fixtures for event bus setup
#   - Integration tests > unit tests (test L1 → L5 → L2 flow)
#
# Performance tests:
#   - Publish 1000 events, measure P95 latency (target: <2ms)
#   - Deliver to 10 subscribers, measure P95 latency (target: <5ms)
#   - End-to-end test: L1 publish → L2 receive (target: <10ms P95)
#
# =============================================================================
