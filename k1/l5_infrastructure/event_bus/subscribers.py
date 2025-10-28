"""
Subscriber Management - Advanced Subscriber Lifecycle and Health Monitoring

Layer: L5 Infrastructure
Component: Event Bus (Subscriber Management)
Priority: P0 (Critical Path)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0004a: Layer 1-2 Event Bus Communication Pattern
      * Subscriber registration and lifecycle management
      * Health monitoring and timeout handling
      * Admin operations (pause, resume, remove slow subscribers)
      * Section: "Component 3: Layer 2 Event Subscriber"
      * Performance: Registration <1ms, health check <5ms

Dependencies:
    Internal:
        - k1.l5_infrastructure.event_bus.event_bus.EventBus (event bus core)
        - k1.l5_infrastructure.event_bus.schemas.Event (event envelope)
        - k1.l5_infrastructure.event_bus.schemas.EventTopic (topic definitions)

    External:
        - asyncio (async runtime)
        - time (timestamp generation)
        - typing (type hints)
        - dataclasses (subscriber metadata)

Connects To:
    Used By:
        - k1.l5_infrastructure.event_bus.event_bus.EventBus (subscriber registry)
        - k1.l2_orchestration.orchestrator (subscriber registration)
        - k1.l2_orchestration.planner (subscriber registration)
        - Admin tools (subscriber health monitoring)

Performance Budgets:
    - Registration: <1ms P95
    - Unregistration: <1ms P95
    - Health check: <5ms P95 (aggregate stats)
    - Subscriber lookup: O(1) by ID, O(n) by topic
    - Slow subscriber removal: <10ms P95 (batch operation)

Observability:
    - Metrics:
        * k1_event_bus_subscribers_total{topic} (gauge: subscriber count per topic)
        * k1_event_bus_subscriber_health{subscriber_id, status} (gauge: health status)
        * k1_event_bus_subscriber_delivery_rate{subscriber_id} (gauge: success rate 0.0-1.0)
        * k1_event_bus_subscriber_latency_ms{subscriber_id} (histogram: P50/P95/P99)

    - Logs:
        * INFO: subscriber_registered (subscriber_id, topics, registered_at)
        * INFO: subscriber_unregistered (subscriber_id, reason)
        * WARNING: subscriber_timeout (subscriber_id, timeout_count, avg_latency_ms)
        * WARNING: subscriber_slow_removed (subscriber_id, timeout_threshold_ms)
        * ERROR: subscriber_failed (subscriber_id, error_count, last_error)

References:
    - ADR-0004a: Event Bus Communication Pattern (subscriber management)
    - Contract: k1/contracts/event_bus/event_schemas.yaml (event payload validation)
    - Test: tests/k1/l5_infrastructure/event_bus/test_subscribers.py
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Internal imports
from k1.l5_infrastructure.event_bus.schemas import Event, EventTopic

# Third-party imports
# None required for subscriber management


# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# Subscriber health thresholds
HEALTH_THRESHOLD_SUCCESS_RATE = 0.9  # 90% success rate = healthy
HEALTH_THRESHOLD_TIMEOUT_COUNT = 5  # >5 timeouts = slow
HEALTH_THRESHOLD_ERROR_COUNT = 3  # >3 errors = failed

# Default timeout for slow subscriber removal
DEFAULT_TIMEOUT_THRESHOLD_MS = 5000  # 5 seconds


# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class SubscriberStatus(Enum):
    """
    Subscriber health status

    States:
        HEALTHY: Normal operation, <90% success rate, low latency
        SLOW: Frequent timeouts (>5), high latency (>5s P95)
        FAILED: Repeated errors (>3), callback exceptions
        PAUSED: Manually paused by admin
    """

    HEALTHY = "healthy"
    SLOW = "slow"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class SubscriberMetadata:
    """
    Subscriber registration metadata with health tracking

    ADR-0004a: Section "Component 3: Layer 2 Event Subscriber"

    Fields:
        subscriber_id: Unique identifier (e.g., "orchestrator_main")
        topics: List of subscribed topics
        callback: Async callback function
        registered_at: Unix timestamp (when registered)
        is_active: Active (True) or paused (False)
        delivery_count: Total events delivered to subscriber
        success_count: Successful deliveries (no timeout/error)
        timeout_count: Delivery timeouts (>5s per callback)
        error_count: Delivery errors (callback exceptions)
        avg_latency_ms: Average delivery latency (rolling average)
        max_latency_ms: Maximum delivery latency observed
        last_delivery_at: Unix timestamp (last successful delivery)
        status: Health status (HEALTHY, SLOW, FAILED, PAUSED)

    Health Classification:
        - HEALTHY: success_rate ≥ 90%, timeout_count ≤ 5, error_count = 0
        - SLOW: timeout_count > 5 OR avg_latency_ms > 5000
        - FAILED: error_count > 3 OR success_rate < 50%
        - PAUSED: Manually paused by admin
    """

    subscriber_id: str
    topics: List[EventTopic]
    callback: Callable[[Event], Awaitable[None]]
    registered_at: float
    is_active: bool = True
    delivery_count: int = 0
    success_count: int = 0
    timeout_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    last_delivery_at: float = 0.0
    status: SubscriberStatus = SubscriberStatus.HEALTHY

    def update_delivery_stats(
        self,
        latency_ms: float,
        success: bool,
        timeout: bool = False,
        error: bool = False,
    ) -> None:
        """
        Update delivery statistics after event delivery

        Args:
            latency_ms: Delivery latency in milliseconds
            success: True if delivery successful
            timeout: True if delivery timed out
            error: True if delivery raised exception

        Updates:
            - delivery_count, success_count, timeout_count, error_count
            - avg_latency_ms (exponential moving average)
            - max_latency_ms
            - last_delivery_at
            - status (recalculate health)

        TODO(@infrastructure-team): Implement delivery stats update
        Assigned to: Issue #L5-2.2.1
        """
        # TODO(@infrastructure-team): Update counters
        self.delivery_count += 1
        if success:
            self.success_count += 1
            self.last_delivery_at = time.time()
        if timeout:
            self.timeout_count += 1
        if error:
            self.error_count += 1

        # TODO(@infrastructure-team): Update latency stats (EMA)
        if self.delivery_count == 1:
            self.avg_latency_ms = latency_ms
        else:
            # Exponential moving average (alpha = 0.2)
            alpha = 0.2
            self.avg_latency_ms = alpha * latency_ms + (1 - alpha) * self.avg_latency_ms

        self.max_latency_ms = max(self.max_latency_ms, latency_ms)

        # TODO(@infrastructure-team): Recalculate health status
        self._recalculate_status()

    def _recalculate_status(self) -> None:
        """
        Recalculate subscriber health status based on delivery stats

        Health Rules:
            - PAUSED: Manually paused (is_active = False)
            - FAILED: error_count > 3 OR success_rate < 50%
            - SLOW: timeout_count > 5 OR avg_latency_ms > 5000
            - HEALTHY: Otherwise (success_rate ≥ 90%, low latency)

        TODO(@infrastructure-team): Implement health status calculation
        Assigned to: Issue #L5-2.2.1
        """
        if not self.is_active:
            self.status = SubscriberStatus.PAUSED
            return

        # Calculate success rate
        success_rate = (
            self.success_count / self.delivery_count if self.delivery_count > 0 else 1.0
        )

        # TODO(@infrastructure-team): Apply health rules
        if self.error_count > HEALTH_THRESHOLD_ERROR_COUNT or success_rate < 0.5:
            self.status = SubscriberStatus.FAILED
        elif (
            self.timeout_count > HEALTH_THRESHOLD_TIMEOUT_COUNT
            or self.avg_latency_ms > DEFAULT_TIMEOUT_THRESHOLD_MS
        ):
            self.status = SubscriberStatus.SLOW
        else:
            self.status = SubscriberStatus.HEALTHY

    def get_health_summary(self) -> Dict[str, Any]:
        """
        Get subscriber health summary for monitoring

        Returns:
            Dict with:
                - status: Health status string
                - success_rate: Percentage successful (0.0-1.0)
                - delivery_count: Total deliveries
                - timeout_count: Total timeouts
                - error_count: Total errors
                - avg_latency_ms: Average latency
                - max_latency_ms: Max latency
                - last_delivery_at: Last delivery timestamp

        TODO(@infrastructure-team): Implement health summary
        Assigned to: Issue #L5-2.2.1
        """
        success_rate = (
            self.success_count / self.delivery_count if self.delivery_count > 0 else 0.0
        )

        return {
            "subscriber_id": self.subscriber_id,
            "status": self.status.value,
            "is_active": self.is_active,
            "success_rate": success_rate,
            "delivery_count": self.delivery_count,
            "success_count": self.success_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "avg_latency_ms": self.avg_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "last_delivery_at": self.last_delivery_at,
            "topics": [topic.value for topic in self.topics],
        }


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class SubscriberRegistry:
    """
    Subscriber Registry: Advanced subscriber lifecycle and health monitoring

    Purpose:
        Centralized registry for all event bus subscribers with health tracking,
        admin operations, and subscriber discovery.

    Responsibilities:
        1. Maintain subscriber registry (register/unregister)
        2. Track subscriber health and delivery stats
        3. Provide subscriber discovery (find by topic/id)
        4. Handle subscriber lifecycle (register → active → paused → unregister)
        5. Admin operations (pause, resume, remove slow subscribers)
        6. Export health metrics for monitoring

    Registry Structure:
        - subscribers_by_id: {subscriber_id → SubscriberMetadata}
        - subscribers_by_topic: {topic → [subscriber_id]}

    Performance Budget (from ADR-0004a):
        - Registration: <1ms P95
        - Unregistration: <1ms P95
        - Health check: <5ms P95 (aggregate stats)
        - Topic lookup: O(n) where n = subscribers for topic (typically <100)
        - ID lookup: O(1)

    Health Monitoring:
        - Automatic status updates after each delivery
        - Admin alerts for SLOW or FAILED subscribers
        - Configurable thresholds for health classification

    ADR-0004a: Section "Component 3: Layer 2 Event Subscriber"
    """

    def __init__(self):
        """
        Initialize subscriber registry

        TODO(@infrastructure-team): Initialize registry data structures
        Assigned to: Issue #L5-2.2.1
        """
        # Subscriber registry by ID (O(1) lookup)
        self.subscribers_by_id: Dict[str, SubscriberMetadata] = {}

        # Subscriber registry by topic (O(n) lookup)
        self.subscribers_by_topic: Dict[EventTopic, List[str]] = {}

        # Stats
        self._total_registrations = 0
        self._total_unregistrations = 0

        logger.info("subscriber_registry_initialized")

    async def register_subscriber(
        self,
        subscriber_id: str,
        topics: List[EventTopic],
        callback: Callable[[Event], Awaitable[None]],
    ) -> SubscriberMetadata:
        """
        Register new subscriber

        Registers async callback for specified topics and creates
        SubscriberMetadata record for health tracking.

        Args:
            subscriber_id: Unique identifier (e.g., "orchestrator_main")
            topics: List of topics to subscribe to
            callback: Async callback function (must be non-blocking)

        Returns:
            SubscriberMetadata with registration details

        Raises:
            ValueError: If subscriber_id already exists or topics empty
            TypeError: If callback not async

        Performance:
            - Registration: <1ms P95

        Usage:
            async def handle_intent(event: Event):
                await orchestrator.process_intent(event)

            metadata = await registry.register_subscriber(
                subscriber_id="orchestrator_main",
                topics=[EventTopic.INTENT_DETECTED, EventTopic.USER_INPUT],
                callback=handle_intent,
            )

        ADR-0004a: Section "Component 3: Layer 2 Event Subscriber"

        TODO(@infrastructure-team): Implement subscriber registration
        Assigned to: Issue #L5-2.2.1

        Steps:
            1. Validate subscriber_id not already registered
            2. Validate topics not empty
            3. Validate callback is async (asyncio.iscoroutinefunction)
            4. Create SubscriberMetadata record
            5. Add to subscribers_by_id
            6. Add to subscribers_by_topic for each topic
            7. Increment _total_registrations
            8. Emit metric: k1_event_bus_subscribers_total{topic}
            9. Log: INFO subscriber_registered
            10. Return metadata
        """
        # TODO(@infrastructure-team): Validate subscriber_id
        if subscriber_id in self.subscribers_by_id:
            raise ValueError(f"Subscriber {subscriber_id} already registered")

        # TODO(@infrastructure-team): Validate topics
        if not topics:
            raise ValueError("Topics list cannot be empty")

        # TODO(@infrastructure-team): Validate callback is async
        if not asyncio.iscoroutinefunction(callback):
            raise TypeError(f"Callback must be async function, got {type(callback)}")

        # TODO(@infrastructure-team): Create subscriber metadata
        metadata = SubscriberMetadata(
            subscriber_id=subscriber_id,
            topics=topics,
            callback=callback,
            registered_at=time.time(),
        )

        # TODO(@infrastructure-team): Add to registries
        self.subscribers_by_id[subscriber_id] = metadata

        for topic in topics:
            if topic not in self.subscribers_by_topic:
                self.subscribers_by_topic[topic] = []
            self.subscribers_by_topic[topic].append(subscriber_id)

        # TODO(@infrastructure-team): Update stats
        self._total_registrations += 1

        # TODO(@infrastructure-team): Emit metrics and logs
        logger.info(
            "subscriber_registered",
            subscriber_id=subscriber_id,
            topics=[topic.value for topic in topics],
            registered_at=metadata.registered_at,
            total_subscribers=len(self.subscribers_by_id),
        )

        return metadata

    async def unregister_subscriber(
        self,
        subscriber_id: str,
        reason: str = "user_request",
    ) -> None:
        """
        Unregister subscriber from all topics

        Removes subscriber from registry and cleans up topic mappings.

        Args:
            subscriber_id: Subscriber to remove
            reason: Unregistration reason (default: "user_request")

        Raises:
            ValueError: If subscriber_id not found

        Performance:
            - Unregistration: <1ms P95

        Reasons:
            - "user_request": Manual unsubscribe
            - "slow_removed": Automatic removal due to timeouts
            - "failed_removed": Automatic removal due to errors
            - "shutdown": Event bus shutdown

        ADR-0004a: Section "Component 3: Layer 2 Event Subscriber"

        TODO(@infrastructure-team): Implement subscriber unregistration
        Assigned to: Issue #L5-2.2.1

        Steps:
            1. Validate subscriber_id exists
            2. Get metadata from subscribers_by_id
            3. Remove from subscribers_by_topic for each topic
            4. Remove from subscribers_by_id
            5. Increment _total_unregistrations
            6. Emit metric: k1_event_bus_subscribers_total{topic}
            7. Log: INFO subscriber_unregistered
        """
        # TODO(@infrastructure-team): Validate subscriber exists
        if subscriber_id not in self.subscribers_by_id:
            raise ValueError(f"Subscriber {subscriber_id} not found")

        # TODO(@infrastructure-team): Get metadata
        metadata = self.subscribers_by_id[subscriber_id]

        # TODO(@infrastructure-team): Remove from topic mappings
        for topic in metadata.topics:
            if topic in self.subscribers_by_topic:
                try:
                    self.subscribers_by_topic[topic].remove(subscriber_id)
                    if not self.subscribers_by_topic[topic]:
                        # Remove empty topic list
                        del self.subscribers_by_topic[topic]
                except ValueError:
                    # Already removed (shouldn't happen, but handle gracefully)
                    logger.warning(
                        "subscriber_not_in_topic",
                        subscriber_id=subscriber_id,
                        topic=topic.value,
                    )

        # TODO(@infrastructure-team): Remove from ID registry
        del self.subscribers_by_id[subscriber_id]

        # TODO(@infrastructure-team): Update stats
        self._total_unregistrations += 1

        # TODO(@infrastructure-team): Emit metrics and logs
        logger.info(
            "subscriber_unregistered",
            subscriber_id=subscriber_id,
            reason=reason,
            total_subscribers=len(self.subscribers_by_id),
        )

    def get_subscribers_by_topic(
        self,
        topic: EventTopic,
    ) -> List[SubscriberMetadata]:
        """
        Get all subscribers for a topic

        Args:
            topic: Topic to query

        Returns:
            List of SubscriberMetadata objects (may be empty)

        Performance:
            - Lookup: O(n) where n = subscribers for topic (typically <100)

        Usage:
            subscribers = registry.get_subscribers_by_topic(EventTopic.INTENT_DETECTED)
            for sub in subscribers:
                if sub.is_active:
                    await sub.callback(event)

        ADR-0004a: Section "Component 3: Layer 2 Event Subscriber"

        TODO(@infrastructure-team): Implement topic-based lookup
        Assigned to: Issue #L5-2.2.1
        """
        # TODO(@infrastructure-team): Get subscriber IDs for topic
        subscriber_ids = self.subscribers_by_topic.get(topic, [])

        # TODO(@infrastructure-team): Resolve IDs to metadata
        return [
            self.subscribers_by_id[sub_id]
            for sub_id in subscriber_ids
            if sub_id in self.subscribers_by_id
        ]

    def get_subscriber_by_id(
        self,
        subscriber_id: str,
    ) -> Optional[SubscriberMetadata]:
        """
        Get subscriber metadata by ID

        Args:
            subscriber_id: Subscriber ID to lookup

        Returns:
            SubscriberMetadata or None if not found

        Performance:
            - Lookup: O(1)

        TODO(@infrastructure-team): Implement ID-based lookup
        Assigned to: Issue #L5-2.2.1
        """
        return self.subscribers_by_id.get(subscriber_id)

    def get_subscriber_health(
        self,
        subscriber_id: str,
    ) -> Dict[str, Any]:
        """
        Get subscriber health status and statistics

        Args:
            subscriber_id: Subscriber to check

        Returns:
            Dict with health summary (see SubscriberMetadata.get_health_summary)

        Raises:
            ValueError: If subscriber_id not found

        Performance:
            - Health check: <1ms (single subscriber)

        Usage:
            health = registry.get_subscriber_health("orchestrator_main")
            if health['status'] == 'slow':
                logger.warning("Orchestrator subscriber is slow", health)

        ADR-0004a: Section "Component 3: Layer 2 Event Subscriber"

        TODO(@infrastructure-team): Implement health status retrieval
        Assigned to: Issue #L5-2.2.1
        """
        # TODO(@infrastructure-team): Get subscriber metadata
        metadata = self.get_subscriber_by_id(subscriber_id)
        if not metadata:
            raise ValueError(f"Subscriber {subscriber_id} not found")

        # TODO(@infrastructure-team): Return health summary
        return metadata.get_health_summary()

    def get_all_health(self) -> List[Dict[str, Any]]:
        """
        Get health status for all subscribers

        Returns:
            List of health summary dicts (one per subscriber)

        Performance:
            - Aggregate health check: <5ms P95 (all subscribers)

        Usage:
            all_health = registry.get_all_health()
            slow_subscribers = [h for h in all_health if h['status'] == 'slow']
            failed_subscribers = [h for h in all_health if h['status'] == 'failed']

        TODO(@infrastructure-team): Implement aggregate health retrieval
        Assigned to: Issue #L5-2.2.1
        """
        return [
            metadata.get_health_summary()
            for metadata in self.subscribers_by_id.values()
        ]

    async def pause_subscriber(
        self,
        subscriber_id: str,
    ) -> None:
        """
        Pause subscriber (stop delivering events)

        Args:
            subscriber_id: Subscriber to pause

        Raises:
            ValueError: If subscriber_id not found

        Admin Operation:
            Manually pauses subscriber without unregistering.
            Events will not be delivered while paused.

        TODO(@infrastructure-team): Implement subscriber pause
        Assigned to: Issue #L5-2.2.1
        """
        metadata = self.get_subscriber_by_id(subscriber_id)
        if not metadata:
            raise ValueError(f"Subscriber {subscriber_id} not found")

        metadata.is_active = False
        metadata.status = SubscriberStatus.PAUSED

        logger.info("subscriber_paused", subscriber_id=subscriber_id)

    async def resume_subscriber(
        self,
        subscriber_id: str,
    ) -> None:
        """
        Resume paused subscriber

        Args:
            subscriber_id: Subscriber to resume

        Raises:
            ValueError: If subscriber_id not found

        Admin Operation:
            Resumes paused subscriber and recalculates health status.

        TODO(@infrastructure-team): Implement subscriber resume
        Assigned to: Issue #L5-2.2.1
        """
        metadata = self.get_subscriber_by_id(subscriber_id)
        if not metadata:
            raise ValueError(f"Subscriber {subscriber_id} not found")

        metadata.is_active = True
        metadata._recalculate_status()

        logger.info(
            "subscriber_resumed",
            subscriber_id=subscriber_id,
            status=metadata.status.value,
        )

    async def remove_slow_subscribers(
        self,
        timeout_threshold_ms: int = DEFAULT_TIMEOUT_THRESHOLD_MS,
    ) -> List[str]:
        """
        Remove subscribers exceeding timeout threshold

        Automatically removes subscribers with status=SLOW or excessive timeouts.

        Args:
            timeout_threshold_ms: Timeout limit in milliseconds (default: 5000ms)

        Returns:
            List of removed subscriber IDs

        Side effects:
            - Unsubscribes slow subscribers
            - Logs WARNING for each removal

        Performance:
            - Batch removal: <10ms P95

        Admin Operation:
            Used to clean up slow subscribers that are blocking event delivery.

        ADR-0004a: Section "Component 3: Layer 2 Event Subscriber"

        TODO(@infrastructure-team): Implement slow subscriber removal
        Assigned to: Issue #L5-2.2.1

        Steps:
            1. Find subscribers with status=SLOW
            2. For each slow subscriber:
               - Log: WARNING subscriber_slow_removed
               - Call unregister_subscriber(reason="slow_removed")
            3. Return list of removed subscriber IDs
        """
        removed_ids = []

        # TODO(@infrastructure-team): Find slow subscribers
        for sub_id, metadata in list(self.subscribers_by_id.items()):
            if metadata.status == SubscriberStatus.SLOW:
                logger.warning(
                    "subscriber_slow_removed",
                    subscriber_id=sub_id,
                    timeout_count=metadata.timeout_count,
                    avg_latency_ms=metadata.avg_latency_ms,
                    timeout_threshold_ms=timeout_threshold_ms,
                )

                # TODO(@infrastructure-team): Unregister slow subscriber
                await self.unregister_subscriber(sub_id, reason="slow_removed")
                removed_ids.append(sub_id)

        if removed_ids:
            logger.info(
                "slow_subscribers_removed",
                removed_count=len(removed_ids),
                removed_ids=removed_ids,
            )

        return removed_ids

    async def remove_failed_subscribers(self) -> List[str]:
        """
        Remove subscribers with status=FAILED

        Automatically removes subscribers with repeated errors.

        Returns:
            List of removed subscriber IDs

        Side effects:
            - Unsubscribes failed subscribers
            - Logs ERROR for each removal

        Admin Operation:
            Used to clean up failed subscribers that are repeatedly raising exceptions.

        TODO(@infrastructure-team): Implement failed subscriber removal
        Assigned to: Issue #L5-2.2.1
        """
        removed_ids = []

        # TODO(@infrastructure-team): Find failed subscribers
        for sub_id, metadata in list(self.subscribers_by_id.items()):
            if metadata.status == SubscriberStatus.FAILED:
                logger.error(
                    "subscriber_failed_removed",
                    subscriber_id=sub_id,
                    error_count=metadata.error_count,
                    success_rate=(
                        metadata.success_count / metadata.delivery_count
                        if metadata.delivery_count > 0
                        else 0.0
                    ),
                )

                # TODO(@infrastructure-team): Unregister failed subscriber
                await self.unregister_subscriber(sub_id, reason="failed_removed")
                removed_ids.append(sub_id)

        if removed_ids:
            logger.error(
                "failed_subscribers_removed",
                removed_count=len(removed_ids),
                removed_ids=removed_ids,
            )

        return removed_ids

    def get_stats(self) -> Dict[str, Any]:
        """
        Get subscriber registry statistics

        Returns:
            Dict with:
                - total_subscribers: Current subscriber count
                - total_registrations: Lifetime registrations
                - total_unregistrations: Lifetime unregistrations
                - subscribers_by_status: Count by status (healthy, slow, failed, paused)
                - topics_with_subscribers: Count of active topics

        Performance:
            - Stats collection: <5ms P95

        TODO(@infrastructure-team): Implement stats collection
        Assigned to: Issue #L5-2.2.1
        """
        # Count subscribers by status
        status_counts = {
            "healthy": 0,
            "slow": 0,
            "failed": 0,
            "paused": 0,
        }

        for metadata in self.subscribers_by_id.values():
            status_counts[metadata.status.value] += 1

        return {
            "total_subscribers": len(self.subscribers_by_id),
            "total_registrations": self._total_registrations,
            "total_unregistrations": self._total_unregistrations,
            "subscribers_by_status": status_counts,
            "topics_with_subscribers": len(self.subscribers_by_topic),
        }


# =============================================================================
# SECTION 5: MODULE EXPORTS
# =============================================================================

__all__ = [
    "SubscriberRegistry",
    "SubscriberMetadata",
    "SubscriberStatus",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_event_bus_subscribers_total{topic} (gauge: subscriber count per topic)
#   - k1_event_bus_subscriber_health{subscriber_id, status} (gauge: health status 0=healthy, 1=slow, 2=failed, 3=paused)
#   - k1_event_bus_subscriber_delivery_rate{subscriber_id} (gauge: success rate 0.0-1.0)
#   - k1_event_bus_subscriber_latency_ms{subscriber_id} (histogram: P50/P95/P99 delivery latency)
#   - k1_event_bus_subscriber_deliveries_total{subscriber_id, status} (counter: delivery count by status)
#
# Logs to emit:
#   - Level: INFO (registration/unregistration), WARNING (slow/timeout), ERROR (failed)
#   - Fields: component="event_bus.subscribers", subscriber_id, topics, status, reason
#   - Events: subscriber_registered, subscriber_unregistered, subscriber_timeout, subscriber_slow_removed, subscriber_failed_removed
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/event_bus/test_subscribers.py
#   - Test: subscriber registration/unregistration
#   - Test: health tracking (delivery stats update)
#   - Test: status transitions (HEALTHY → SLOW → FAILED)
#   - Test: subscriber discovery (by topic, by ID)
#   - Test: pause/resume subscriber
#   - Test: remove slow subscribers (timeout threshold)
#   - Test: remove failed subscribers (error threshold)
#   - Test: aggregate health monitoring (get_all_health)
#   - Test: performance budgets (<1ms registration, <5ms health check)
#
# No simulation code allowed:
#   - Use real callback functions
#   - Test with actual event delivery
#   - Integration tests > unit tests
#
# =============================================================================
