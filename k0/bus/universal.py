"""Universal bus facade for topic-based stream routing (ADR-055)."""

from __future__ import annotations

import asyncio
from typing import Iterable

from .core import BusDispatcher, BusMessage

__all__ = ["UniversalBus"]


class UniversalBus:
    """Topic-based router that dispatches to appropriate bus stream.

    Routes messages to streams based on topic namespace:
    - feedback.* → feedback stream (non-WAL, id-based idempotency)
    - everything else → wal stream (WAL-backed, monotonic offsets)

    This ensures developers cannot accidentally publish feedback to WAL stream
    or vice versa, enforcing correctness at the architectural level (ADR-055).

    Example:
        wal_dispatcher = BusDispatcher(scheduler, stream="wal", port="bus_wal")
        feedback_dispatcher = BusDispatcher(scheduler, stream="feedback", port="bus_feedback")
        bus = UniversalBus(wal_dispatcher, feedback_dispatcher)

        # Automatically routes to correct stream based on topic
        await bus.dispatch([
            BusMessage(topic="cognitive.memory.write.committed.v1", ...),  # → wal
            BusMessage(topic="feedback.p02.reformulation.v1", ...),        # → feedback
        ])
    """

    def __init__(
        self,
        wal_dispatcher: BusDispatcher,
        feedback_dispatcher: BusDispatcher,
    ) -> None:
        """Initialize universal bus with stream-specific dispatchers.

        Args:
            wal_dispatcher: BusDispatcher configured with stream="wal"
            feedback_dispatcher: BusDispatcher configured with stream="feedback"
        """
        self._wal = wal_dispatcher
        self._feedback = feedback_dispatcher

    async def dispatch(self, messages: Iterable[BusMessage]) -> None:
        """Route messages to appropriate stream based on topic prefix.

        Routes feedback.* topics to feedback stream, all others to WAL stream.
        Enforces stream-specific requirements:
        - WAL stream: requires message.offset (monotonic)
        - Feedback stream: requires metadata['message_id']

        Args:
            messages: Messages to dispatch (can be mixed WAL + feedback)

        Raises:
            ValueError: If message violates stream requirements. For example:
                - WAL message missing offset
                - Feedback message missing metadata['message_id']
                - WAL messages with non-monotonic offsets
        """
        batch = list(messages)
        if not batch:
            return

        # Partition messages by topic namespace
        wal_messages = [m for m in batch if not m.topic.startswith("feedback.")]
        feedback_messages = [m for m in batch if m.topic.startswith("feedback.")]

        # Dispatch to both streams concurrently (if both have messages)
        tasks = []
        if wal_messages:
            tasks.append(self._wal.dispatch(wal_messages))
        if feedback_messages:
            tasks.append(self._feedback.dispatch(feedback_messages))

        if tasks:
            await asyncio.gather(*tasks)
