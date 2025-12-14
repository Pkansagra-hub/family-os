"""
Mailbox Manager (Singleton for Mailbox Routing & Management)

Manages mailboxes for all agents and provides routing logic.

Related ADRs:
- ADR-0002a: Mailbox MPSC Queue Implementation
- ADR-0005: Agent Lifecycle FSM

Performance Targets:
- Routing: <0.1ms P95 (dictionary lookup)
- Broadcast: <1ms P95 for 10 receivers
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from .mailbox import Mailbox, Message, Priority

logger = logging.getLogger(__name__)


class MailboxManager:
    """
    Singleton manager for all agent mailboxes.

    Responsibilities:
    - Create/delete mailboxes for agents
    - Route messages to correct agent mailbox
    - Broadcast messages to multiple agents
    - Track metrics (message count, latency, queue depths)

    Thread-safe for concurrent access.
    """

    _instance: Optional["MailboxManager"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize mailbox manager (only once due to singleton)"""
        if self._initialized:
            return

        self._mailboxes: dict[str, Mailbox] = {}  # agent_id -> Mailbox
        self._creation_time = datetime.now()

        # Metrics
        self._total_messages_routed = 0
        self._total_broadcasts = 0
        self._routing_errors = 0

        self._initialized = True
        logger.info("[MailboxManager] Initialized singleton instance")

    async def create_mailbox(self, agent_id: str, capacity: int = 64) -> Mailbox:
        """
        Create new mailbox for agent.

        Args:
            agent_id: UUID of agent
            capacity: Total mailbox capacity (default: 64)

        Returns:
            Created Mailbox instance

        Raises:
            ValueError: If mailbox already exists for agent_id
        """
        async with self._lock:
            if agent_id in self._mailboxes:
                raise ValueError(f"Mailbox already exists for agent {agent_id}")

            mailbox = Mailbox(agent_id=agent_id, capacity=capacity)
            self._mailboxes[agent_id] = mailbox

            logger.info(f"[MailboxManager] Created mailbox for agent {agent_id}")
            return mailbox

    def get_mailbox(self, agent_id: str) -> Optional[Mailbox]:
        """
        Retrieve agent's mailbox (non-blocking, no async).

        Args:
            agent_id: UUID of agent

        Returns:
            Mailbox instance or None if not found
        """
        return self._mailboxes.get(agent_id)

    async def delete_mailbox(self, agent_id: str) -> bool:
        """
        Remove mailbox (agent terminated).

        Args:
            agent_id: UUID of agent

        Returns:
            True if deleted, False if not found
        """
        async with self._lock:
            if agent_id not in self._mailboxes:
                logger.warning(f"[MailboxManager] No mailbox found for agent {agent_id}")
                return False

            del self._mailboxes[agent_id]
            logger.info(f"[MailboxManager] Deleted mailbox for agent {agent_id}")
            return True

    async def send_message(
        self,
        sender_id: str,
        receiver_id: str,
        payload: dict,
        priority: Priority = Priority.STANDARD,
        trace_id: str = "",
    ) -> bool:
        """
        Route message to receiver's mailbox.

        Args:
            sender_id: UUID of sending agent
            receiver_id: UUID of receiving agent
            payload: Message payload (dictionary)
            priority: Message priority (default: STANDARD)
            trace_id: Cognitive trace ID for distributed tracing

        Returns:
            True if sent successfully, False if receiver not found or mailbox full
        """
        # Lookup receiver's mailbox
        receiver_mailbox = self.get_mailbox(receiver_id)

        if receiver_mailbox is None:
            logger.warning(
                f"[MailboxManager] Receiver {receiver_id} not found, "
                f"cannot deliver message from {sender_id}"
            )
            self._routing_errors += 1
            return False

        # Create message
        message = Message(
            sender_id=sender_id,
            receiver_id=receiver_id,
            priority=priority,
            payload=payload,
            trace_id=trace_id,
        )

        # Send to mailbox
        try:
            success = await receiver_mailbox.send(message)

            if success:
                self._total_messages_routed += 1
                logger.debug(
                    f"[MailboxManager] Routed {priority.name} message "
                    f"{message.message_id} from {sender_id} to {receiver_id}"
                )
            else:
                # Message dropped due to backpressure
                self._routing_errors += 1
                logger.warning(
                    f"[MailboxManager] Message {message.message_id} dropped "
                    f"(mailbox full for {receiver_id})"
                )

            return success

        except Exception as e:
            logger.error(
                f"[MailboxManager] Error sending message from {sender_id} " f"to {receiver_id}: {e}"
            )
            self._routing_errors += 1
            return False

    async def broadcast(
        self,
        sender_id: str,
        receiver_ids: list[str],
        payload: dict,
        priority: Priority = Priority.STANDARD,
        trace_id: str = "",
    ) -> dict[str, bool]:
        """
        Send message to multiple agents.

        Args:
            sender_id: UUID of sending agent
            receiver_ids: List of receiver agent UUIDs
            payload: Message payload (dictionary)
            priority: Message priority (default: STANDARD)
            trace_id: Cognitive trace ID for distributed tracing

        Returns:
            Dictionary mapping receiver_id -> success (True/False)
        """
        results = {}

        # Send to all receivers concurrently
        tasks = [
            self.send_message(
                sender_id=sender_id,
                receiver_id=receiver_id,
                payload=payload,
                priority=priority,
                trace_id=trace_id,
            )
            for receiver_id in receiver_ids
        ]

        successes = await asyncio.gather(*tasks, return_exceptions=True)

        for receiver_id, success in zip(receiver_ids, successes):
            # Check if exception occurred
            if isinstance(success, Exception):
                logger.error(f"[MailboxManager] Broadcast to {receiver_id} failed: {success}")
                results[receiver_id] = False
            else:
                results[receiver_id] = success

        self._total_broadcasts += 1

        success_count = sum(1 for s in results.values() if s)
        logger.info(
            f"[MailboxManager] Broadcast from {sender_id} to {len(receiver_ids)} agents: "
            f"{success_count}/{len(receiver_ids)} successful"
        )

        return results

    def get_stats(self) -> dict:
        """
        Get manager statistics for monitoring.

        Returns:
            Dictionary with metrics:
            - total_mailboxes: Number of active mailboxes
            - total_messages_routed: Total messages routed
            - total_broadcasts: Total broadcasts sent
            - routing_errors: Messages that failed to route
            - queue_depths: Current depth per agent
            - uptime_seconds: Manager uptime
        """
        uptime = (datetime.now() - self._creation_time).total_seconds()

        queue_depths = {agent_id: mailbox.size() for agent_id, mailbox in self._mailboxes.items()}

        return {
            "total_mailboxes": len(self._mailboxes),
            "total_messages_routed": self._total_messages_routed,
            "total_broadcasts": self._total_broadcasts,
            "routing_errors": self._routing_errors,
            "queue_depths": queue_depths,
            "uptime_seconds": uptime,
        }

    def get_all_mailbox_stats(self) -> dict[str, dict]:
        """
        Get detailed statistics for all mailboxes.

        Returns:
            Dictionary mapping agent_id -> mailbox stats
        """
        return {agent_id: mailbox.get_stats() for agent_id, mailbox in self._mailboxes.items()}


# Example usage
if __name__ == "__main__":
    import asyncio

    async def example():
        # Create manager (singleton)
        manager = MailboxManager()

        # Create mailboxes for 3 agents
        await manager.create_mailbox("agent_A")
        await manager.create_mailbox("agent_B")
        await manager.create_mailbox("agent_C")

        # Send message from A to B
        await manager.send_message(
            sender_id="agent_A",
            receiver_id="agent_B",
            payload={"type": "GREETING", "data": "Hello from A"},
            priority=Priority.STANDARD,
            trace_id="trace_001",
        )

        # Broadcast from A to B and C
        results = await manager.broadcast(
            sender_id="agent_A",
            receiver_ids=["agent_B", "agent_C"],
            payload={"type": "ANNOUNCEMENT", "data": "Hello everyone"},
            priority=Priority.URGENT,
            trace_id="trace_002",
        )
        print(f"Broadcast results: {results}")

        # Get manager stats
        stats = manager.get_stats()
        print(f"\nManager stats: {stats}")

        # Get mailbox stats
        mailbox_stats = manager.get_all_mailbox_stats()
        print(f"\nMailbox stats: {mailbox_stats}")

        # Receive messages (agent B)
        mailbox_b = manager.get_mailbox("agent_B")
        if mailbox_b:
            msg1 = await mailbox_b.receive()
            print(f"\nAgent B received: {msg1.priority.name} - {msg1.payload}")

            msg2 = await mailbox_b.receive()
            print(f"Agent B received: {msg2.priority.name} - {msg2.payload}")

    asyncio.run(example())
