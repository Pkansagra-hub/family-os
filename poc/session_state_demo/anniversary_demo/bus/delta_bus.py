"""
Delta Bus - Pub/Sub Message Broker
==================================

Provides asynchronous message passing between agents and the Concierge.

Topics:
- agent.search.result: SearchAgent results
- agent.booking.result: BookingAgent confirmations
- agent.monitor.alert: Background monitor alerts
- concierge.command: Commands from Concierge to agents

Features:
- Async publish/subscribe
- Topic-based routing
- Message history (configurable depth)
- Wildcard subscriptions (e.g., "agent.*")

Reference: FULL_ARCHITECTURE_IMPLEMENTATION_PLAN.md - Milestone 8.4
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# MESSAGE FORMAT
# =============================================================================


@dataclass
class Message:
    """
    A message on the Delta Bus.

    Attributes:
        topic: Message topic (e.g., "agent.search.result")
        payload: Message content (AgentResult, alert, etc.)
        message_id: Unique message ID
        timestamp: When the message was published
        source: ID of the publisher
        correlation_id: Optional ID to correlate request/response
    """

    topic: str
    payload: Any
    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "topic": self.topic,
            "payload": (
                self.payload if not hasattr(self.payload, "to_dict") else self.payload.to_dict()
            ),
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "correlation_id": self.correlation_id,
        }


@dataclass
class Subscription:
    """
    A subscription to the Delta Bus.

    Attributes:
        subscriber_id: ID of the subscriber
        topic_pattern: Topic pattern (supports wildcards like "agent.*")
        callback: Async callback function
        active: Whether subscription is active
    """

    subscriber_id: str
    topic_pattern: str
    callback: Callable[[Message], Awaitable[None]]
    active: bool = True
    subscription_id: str = field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:8]}")


# =============================================================================
# DELTA BUS IMPLEMENTATION
# =============================================================================


class DeltaBus:
    """
    Asynchronous pub/sub message broker.

    Usage:
        bus = DeltaBus()

        # Subscribe to agent results
        await bus.subscribe(
            subscriber_id="concierge",
            topic_pattern="agent.*.result",
            callback=handle_agent_result,
        )

        # Publish a result
        await bus.publish(
            topic="agent.search.result",
            message=search_result,
            source="search_agent_001",
        )
    """

    def __init__(self, history_depth: int = 100):
        """
        Initialize Delta Bus.

        Args:
            history_depth: Number of messages to keep in history
        """
        self._subscriptions: Dict[str, Subscription] = {}
        self._history: List[Message] = []
        self._history_depth = history_depth
        self._lock = asyncio.Lock()

        # Statistics
        self._messages_published = 0
        self._messages_delivered = 0
        self._delivery_failures = 0

    # =========================================================================
    # SUBSCRIPTION MANAGEMENT
    # =========================================================================

    async def subscribe(
        self,
        subscriber_id: str,
        topic_pattern: str,
        callback: Callable[[Message], Awaitable[None]],
    ) -> str:
        """
        Subscribe to messages matching a topic pattern.

        Args:
            subscriber_id: ID of the subscriber
            topic_pattern: Topic pattern (supports * wildcard)
            callback: Async callback to invoke on message

        Returns:
            Subscription ID
        """
        subscription = Subscription(
            subscriber_id=subscriber_id,
            topic_pattern=topic_pattern,
            callback=callback,
        )

        async with self._lock:
            self._subscriptions[subscription.subscription_id] = subscription

        logger.info(f"Subscription created: {subscriber_id} -> {topic_pattern}")
        return subscription.subscription_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a subscription.

        Args:
            subscription_id: ID of the subscription to remove

        Returns:
            True if removed, False if not found
        """
        async with self._lock:
            if subscription_id in self._subscriptions:
                del self._subscriptions[subscription_id]
                logger.info(f"Subscription removed: {subscription_id}")
                return True
            return False

    def _matches_pattern(self, topic: str, pattern: str) -> bool:
        """
        Check if a topic matches a pattern.

        Supports wildcards:
        - * matches any single segment
        - # matches any number of segments

        Args:
            topic: The actual topic
            pattern: The subscription pattern

        Returns:
            True if topic matches pattern
        """
        # Convert to fnmatch-style pattern
        import re as re_module

        pattern = pattern.replace(".", "\\.").replace("*", "[^.]*").replace("#", ".*")
        return bool(re_module.match(f"^{pattern}$", topic))

    # =========================================================================
    # PUBLISHING
    # =========================================================================

    async def publish(
        self,
        topic: str,
        message: Any,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Message:
        """
        Publish a message to a topic.

        Args:
            topic: The topic to publish to
            message: The message payload
            source: Optional source ID
            correlation_id: Optional correlation ID

        Returns:
            The published Message
        """
        msg = Message(
            topic=topic,
            payload=message,
            source=source,
            correlation_id=correlation_id,
        )

        self._messages_published += 1

        # Add to history
        async with self._lock:
            self._history.append(msg)
            if len(self._history) > self._history_depth:
                self._history = self._history[-self._history_depth :]

        # Find matching subscriptions and deliver
        matching_subs = []
        async with self._lock:
            for sub in self._subscriptions.values():
                if sub.active and self._matches_pattern(topic, sub.topic_pattern):
                    matching_subs.append(sub)

        # Deliver to all matching subscribers
        delivery_tasks = []
        for sub in matching_subs:
            delivery_tasks.append(self._deliver(msg, sub))

        if delivery_tasks:
            await asyncio.gather(*delivery_tasks, return_exceptions=True)

        logger.debug(f"Published: {topic} -> {len(matching_subs)} subscribers")
        return msg

    async def _deliver(self, message: Message, subscription: Subscription) -> None:
        """
        Deliver a message to a subscriber.

        Args:
            message: The message to deliver
            subscription: The subscription to deliver to
        """
        try:
            await subscription.callback(message)
            self._messages_delivered += 1
        except Exception as e:
            self._delivery_failures += 1
            logger.error(f"Delivery failed to {subscription.subscriber_id}: {e}")

    # =========================================================================
    # QUERYING
    # =========================================================================

    def get_history(
        self,
        topic_pattern: Optional[str] = None,
        limit: int = 10,
    ) -> List[Message]:
        """
        Get message history.

        Args:
            topic_pattern: Optional pattern to filter by
            limit: Maximum messages to return

        Returns:
            List of messages (newest first)
        """
        messages = list(reversed(self._history))

        if topic_pattern:
            messages = [m for m in messages if self._matches_pattern(m.topic, topic_pattern)]

        return messages[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """Get bus statistics."""
        return {
            "subscriptions_active": len([s for s in self._subscriptions.values() if s.active]),
            "history_size": len(self._history),
            "messages_published": self._messages_published,
            "messages_delivered": self._messages_delivered,
            "delivery_failures": self._delivery_failures,
        }

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    async def publish_agent_result(
        self,
        agent_type: str,
        result: Any,
        agent_id: str,
    ) -> Message:
        """
        Convenience method to publish agent results.

        Args:
            agent_type: Type of agent (search, booking, etc.)
            result: The agent result
            agent_id: The agent's ID

        Returns:
            Published message
        """
        return await self.publish(
            topic=f"agent.{agent_type}.result",
            message=result,
            source=agent_id,
        )

    async def publish_alert(
        self,
        alert_type: str,
        alert_data: Any,
        source: str = "monitor",
    ) -> Message:
        """
        Convenience method to publish alerts.

        Args:
            alert_type: Type of alert (weather, price, etc.)
            alert_data: Alert data
            source: Alert source

        Returns:
            Published message
        """
        return await self.publish(
            topic=f"alert.{alert_type}",
            message=alert_data,
            source=source,
        )

    async def wait_for_message(
        self,
        topic_pattern: str,
        timeout: float = 30.0,
        correlation_id: Optional[str] = None,
    ) -> Optional[Message]:
        """
        Wait for a message matching criteria.

        Args:
            topic_pattern: Topic pattern to wait for
            timeout: Timeout in seconds
            correlation_id: Optional correlation ID to match

        Returns:
            The matching message, or None if timeout
        """
        result: Optional[Message] = None
        event = asyncio.Event()

        async def handler(msg: Message) -> None:
            nonlocal result
            if correlation_id and msg.correlation_id != correlation_id:
                return
            result = msg
            event.set()

        sub_id = await self.subscribe(
            subscriber_id=f"waiter_{uuid.uuid4().hex[:8]}",
            topic_pattern=topic_pattern,
            callback=handler,
        )

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            await self.unsubscribe(sub_id)

        return result
