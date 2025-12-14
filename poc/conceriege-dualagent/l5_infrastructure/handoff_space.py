"""
Shared Handoff Space - In-Memory Topic-Based Queue System
Implements pub/sub pattern for Reactive, Proactive, and Specialist communication
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict

logger = logging.getLogger(__name__)


class HandoffSpace:
    """
    In-memory topic-based message queue for POC
    Supports: job.request.{thread_id}, job.clarification.{thread_id}, etc.
    """

    def __init__(self):
        # Topic -> List of subscriber queues
        self._subscribers: Dict[str, list[asyncio.Queue]] = defaultdict(list)
        # Topic -> List of messages (for history/debugging)
        self._message_history: Dict[str, list[Any]] = defaultdict(list)

    def subscribe(self, topic_pattern: str) -> asyncio.Queue:
        """
        Subscribe to a topic pattern
        Returns a queue that will receive messages
        """
        queue = asyncio.Queue(maxsize=100)
        self._subscribers[topic_pattern].append(queue)
        logger.info(f"Subscribed to topic: {topic_pattern}")
        return queue

    async def publish(self, topic: str, message: Any):
        """
        Publish message to topic
        Fans out to all subscribers matching the topic pattern
        """
        logger.info(f"Publishing to {topic}: {type(message).__name__}")

        # Store in history
        self._message_history[topic].append(message)

        # Find matching subscribers (exact match for POC, can extend to wildcards)
        for pattern, queues in self._subscribers.items():
            if self._matches_pattern(topic, pattern):
                for queue in queues:
                    try:
                        await asyncio.wait_for(queue.put(message), timeout=1.0)
                    except asyncio.TimeoutError:
                        logger.warning(f"Queue full for topic {topic}, dropping message")

    def _matches_pattern(self, topic: str, pattern: str) -> bool:
        """Simple pattern matching (can extend to wildcards later)"""
        # For POC: exact match or pattern ends with wildcard
        if pattern.endswith("*"):
            return topic.startswith(pattern[:-1])
        return topic == pattern

    def get_history(self, topic: str) -> list[Any]:
        """Get message history for debugging"""
        return self._message_history.get(topic, [])

    async def close(self):
        """Cleanup all queues"""
        for queues in self._subscribers.values():
            for queue in queues:
                # Drain queue
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break


# Global singleton for POC
_handoff_space: HandoffSpace | None = None


def get_handoff_space() -> HandoffSpace:
    """Get or create global handoff space singleton"""
    global _handoff_space
    if _handoff_space is None:
        _handoff_space = HandoffSpace()
    return _handoff_space
