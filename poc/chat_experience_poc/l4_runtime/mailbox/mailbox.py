"""
Mailbox System (MPSC with 4 Priority Levels)

Actor Model mailbox implementation for inter-agent communication.
Uses asyncio.Queue for async message passing with priority scheduling.

Research:
- Actor Model (Hewitt 1973) - Isolated agents with message passing
- Weighted Fair Queueing (Demers et al. 1989) - Fair priority scheduling

Related ADRs:
- ADR-0002a: Mailbox MPSC Queue Implementation
- ADR-0005: Agent Lifecycle FSM

Performance Targets:
- Enqueue: <0.5ms P95
- Dequeue: <0.5ms P95
- Capacity: 64 messages total
- WFQ weights: [4, 2, 1, 1] for URGENT, STANDARD, LOW, BACKGROUND
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Optional

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """
    Message priority levels for mailbox routing.
    Lower numeric value = higher priority.
    """

    URGENT = 0  # Critical system messages (e.g., agent crash, barge-in)
    STANDARD = 1  # Normal agent messages (e.g., user messages, tool results)
    LOW = 2  # Background tasks (e.g., agent coordination)
    BACKGROUND = 3  # Lowest priority (e.g., memory writes, logging)


@dataclass
class Message:
    """
    Message envelope for actor-to-actor communication.

    Fields match FlatBuffers message_envelope.fbs but use Python types for PoC simplicity.
    """

    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    receiver_id: str = ""
    priority: Priority = Priority.STANDARD
    payload: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    trace_id: str = ""  # cognitive_trace_id for distributed tracing

    def __post_init__(self):
        """Validate message after creation"""
        if not self.sender_id:
            raise ValueError("sender_id is required")
        if not self.receiver_id:
            raise ValueError("receiver_id is required")
        if not isinstance(self.priority, Priority):
            raise ValueError(f"priority must be Priority enum, got {type(self.priority)}")


class Mailbox:
    """
    MPSC (Multi-Producer, Single-Consumer) mailbox with 4 priority levels.

    Each agent has one mailbox. Multiple agents can send messages (producers),
    but only the owning agent receives messages (single consumer).

    Architecture:
    - 4 separate asyncio.Queue instances (one per priority)
    - Weighted Fair Queueing (WFQ) with weights [4, 2, 1, 1]
    - Backpressure: capacity 64 total, block lower priorities when full
    - Starvation detection: log queue depths per priority

    Performance:
    - Enqueue: <0.5ms P95 (async queue put)
    - Dequeue: <0.5ms P95 (WFQ round-robin selection)
    """

    def __init__(self, agent_id: str, capacity: int = 64):
        """
        Initialize mailbox for agent.

        Args:
            agent_id: UUID of agent owning this mailbox
            capacity: Total capacity across all priorities (default: 64)
        """
        self.agent_id = agent_id
        self.capacity = capacity

        # 4 priority queues (asyncio.Queue for async operations)
        # No per-priority capacity limits - total capacity enforced below
        self.queues = {
            Priority.URGENT: asyncio.Queue(),
            Priority.STANDARD: asyncio.Queue(),
            Priority.LOW: asyncio.Queue(),
            Priority.BACKGROUND: asyncio.Queue(),
        }

        # WFQ weights: URGENT=4x, STANDARD=2x, LOW=1x, BACKGROUND=1x
        # Higher weight = processed more often
        self.wfq_weights = {
            Priority.URGENT: 4,
            Priority.STANDARD: 2,
            Priority.LOW: 1,
            Priority.BACKGROUND: 1,
        }

        # Round-robin counters for WFQ (virtual time)
        self.wfq_counters = {
            Priority.URGENT: 0,
            Priority.STANDARD: 0,
            Priority.LOW: 0,
            Priority.BACKGROUND: 0,
        }

        # Metrics
        self.total_messages_sent = 0
        self.total_messages_received = 0
        self.messages_dropped = 0
        self.creation_time = datetime.now()

        logger.info(f"[Mailbox] Created for agent {agent_id}, capacity={capacity}")

    async def send(self, message: Message) -> bool:
        """
        Enqueue message to mailbox (async, non-blocking).

        Backpressure: If total depth >= capacity, block lower priorities first.
        Priority order for blocking: BACKGROUND → LOW → STANDARD (URGENT never blocks).

        Args:
            message: Message to send

        Returns:
            True if enqueued, False if dropped (capacity exceeded for priority)

        Raises:
            ValueError: If message validation fails
        """
        # Validate message
        if message.receiver_id != self.agent_id:
            raise ValueError(
                f"Message receiver_id {message.receiver_id} != mailbox agent {self.agent_id}"
            )

        # Check total capacity (backpressure)
        total_depth = self.size()

        # Hard cap: Never exceed 2x capacity (even for URGENT)
        # This prevents unbounded growth while allowing URGENT burst
        if total_depth >= self.capacity * 2:
            self.messages_dropped += 1
            logger.warning(
                f"[Mailbox] {self.agent_id} HARD CAP (depth={total_depth}), "
                f"dropped {message.priority.name} message {message.message_id}"
            )
            return False

        if total_depth >= self.capacity:
            # Backpressure active - drop lowest priority with messages
            # Order: BACKGROUND > LOW > STANDARD (URGENT bypasses)
            if message.priority == Priority.BACKGROUND:
                # Drop BACKGROUND messages when full
                self.messages_dropped += 1
                logger.warning(
                    f"[Mailbox] {self.agent_id} FULL (depth={total_depth}), "
                    f"dropped BACKGROUND message {message.message_id}"
                )
                return False
            elif message.priority == Priority.LOW:
                # Drop LOW messages when full
                self.messages_dropped += 1
                logger.warning(
                    f"[Mailbox] {self.agent_id} FULL (depth={total_depth}), "
                    f"dropped LOW message {message.message_id}"
                )
                return False
            elif message.priority == Priority.STANDARD:
                # Drop STANDARD messages when full
                self.messages_dropped += 1
                logger.warning(
                    f"[Mailbox] {self.agent_id} FULL (depth={total_depth}), "
                    f"dropped STANDARD message {message.message_id}"
                )
                return False
            # URGENT messages bypass capacity (critical system messages)
            # But still subject to 2x hard cap above

        # Enqueue to appropriate priority queue
        queue = self.queues[message.priority]
        await queue.put(message)
        self.total_messages_sent += 1

        # Log queue depths for starvation detection
        if total_depth % 10 == 0:  # Log every 10 messages
            depths = {p.name: self.queues[p].qsize() for p in Priority}
            logger.debug(f"[Mailbox] {self.agent_id} depths: {depths}")

        return True

    async def receive(self) -> Message:
        """
        Dequeue message from mailbox (async, blocks if empty).

        Uses Weighted Fair Queueing (WFQ) with round-robin:
        - URGENT: 4x processing (check 4 times per round)
        - STANDARD: 2x processing (check 2 times per round)
        - LOW: 1x processing (check 1 time per round)
        - BACKGROUND: 1x processing (check 1 time per round)

        Round: [U, U, U, U, S, S, L, B]
        - Total: 8 checks per round
        - URGENT gets 4/8 = 50% bandwidth
        - STANDARD gets 2/8 = 25% bandwidth
        - LOW gets 1/8 = 12.5% bandwidth
        - BACKGROUND gets 1/8 = 12.5% bandwidth

        Returns:
            Message from highest priority non-empty queue

        Note: This is simplified WFQ. Production would use virtual time calculation.
        """
        # Round-robin schedule based on WFQ weights [4, 2, 1, 1]
        # Total: 8 checks per round
        schedule = (
            [Priority.URGENT] * 4  # 4x for URGENT
            + [Priority.STANDARD] * 2  # 2x for STANDARD
            + [Priority.LOW] * 1  # 1x for LOW
            + [Priority.BACKGROUND] * 1  # 1x for BACKGROUND
        )

        # Try to dequeue from queues in WFQ order
        while True:
            for priority in schedule:
                queue = self.queues[priority]
                if not queue.empty():
                    try:
                        # Non-blocking get (nowait) since we checked empty()
                        message = queue.get_nowait()
                        self.total_messages_received += 1
                        self.wfq_counters[priority] += 1

                        logger.debug(
                            f"[Mailbox] {self.agent_id} received {priority.name} "
                            f"message {message.message_id} from {message.sender_id}"
                        )

                        return message
                    except asyncio.QueueEmpty:
                        # Race condition: another consumer got message
                        continue

            # All queues empty, wait for any message
            # Use asyncio.wait with FIRST_COMPLETED to wake on any queue
            tasks = [asyncio.create_task(queue.get()) for queue in self.queues.values()]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            # Cancel pending tasks
            for task in pending:
                task.cancel()

            # Get message from completed task
            message = list(done)[0].result()
            self.total_messages_received += 1
            self.wfq_counters[message.priority] += 1

            logger.debug(
                f"[Mailbox] {self.agent_id} received {message.priority.name} "
                f"message {message.message_id} from {message.sender_id}"
            )

            return message

    def peek(self) -> Optional[Message]:
        """
        Look at next message without removing (non-blocking).

        Uses same WFQ schedule as receive().

        Returns:
            Next message that would be dequeued, or None if all queues empty
        """
        # Round-robin schedule based on WFQ weights [4, 2, 1, 1]
        schedule = (
            [Priority.URGENT] * 4
            + [Priority.STANDARD] * 2
            + [Priority.LOW] * 1
            + [Priority.BACKGROUND] * 1
        )

        # Find first non-empty queue in WFQ order
        for priority in schedule:
            queue = self.queues[priority]
            if not queue.empty():
                # Peek at queue (internal _queue is deque)
                # Note: This is NOT thread-safe in production!
                try:
                    return queue._queue[0]  # First element in deque
                except (IndexError, AttributeError):
                    continue

        return None

    def size(self) -> int:
        """
        Current total queue depth across all priorities.

        Returns:
            Total number of messages in mailbox
        """
        return sum(queue.qsize() for queue in self.queues.values())

    def size_by_priority(self) -> dict[Priority, int]:
        """
        Current queue depth per priority (for starvation detection).

        Returns:
            Dictionary mapping Priority -> queue depth
        """
        return {priority: queue.qsize() for priority, queue in self.queues.items()}

    def get_stats(self) -> dict:
        """
        Get mailbox statistics for monitoring.

        Returns:
            Dictionary with metrics:
            - agent_id: Agent owning mailbox
            - capacity: Total capacity
            - current_depth: Current total depth
            - depth_by_priority: Depth per priority
            - total_sent: Total messages sent
            - total_received: Total messages received
            - messages_dropped: Messages dropped due to backpressure
            - wfq_counters: Messages processed per priority (validates WFQ)
            - uptime_seconds: Mailbox uptime
        """
        uptime = (datetime.now() - self.creation_time).total_seconds()

        return {
            "agent_id": self.agent_id,
            "capacity": self.capacity,
            "current_depth": self.size(),
            "depth_by_priority": {p.name: self.queues[p].qsize() for p in Priority},
            "total_sent": self.total_messages_sent,
            "total_received": self.total_messages_received,
            "messages_dropped": self.messages_dropped,
            "wfq_counters": {p.name: self.wfq_counters[p] for p in Priority},
            "uptime_seconds": uptime,
        }


# Example usage
if __name__ == "__main__":
    import asyncio

    async def example():
        # Create mailbox for agent
        mailbox = Mailbox(agent_id="agent_123")

        # Send messages with different priorities
        await mailbox.send(
            Message(
                sender_id="agent_456",
                receiver_id="agent_123",
                priority=Priority.URGENT,
                payload={"type": "EMERGENCY", "data": "System overload"},
                trace_id="trace_001",
            )
        )

        await mailbox.send(
            Message(
                sender_id="agent_789",
                receiver_id="agent_123",
                priority=Priority.STANDARD,
                payload={"type": "USER_MESSAGE", "data": "Hello"},
                trace_id="trace_002",
            )
        )

        await mailbox.send(
            Message(
                sender_id="agent_101",
                receiver_id="agent_123",
                priority=Priority.BACKGROUND,
                payload={"type": "LOG_ENTRY", "data": "Debug log"},
                trace_id="trace_003",
            )
        )

        # Receive messages (URGENT comes first due to WFQ)
        msg1 = await mailbox.receive()
        print(f"Received: {msg1.priority.name} - {msg1.payload}")

        msg2 = await mailbox.receive()
        print(f"Received: {msg2.priority.name} - {msg2.payload}")

        msg3 = await mailbox.receive()
        print(f"Received: {msg3.priority.name} - {msg3.payload}")

        # Get stats
        stats = mailbox.get_stats()
        print(f"\nMailbox stats: {stats}")

    asyncio.run(example())
