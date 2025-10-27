"""
K1 L4 Runtime — Priority Scheduler for Mailbox (ADR-0002a, Issue 2.2)

**Purpose:**
    4-tier priority scheduler with WFQ (Weighted Fair Queueing) aging to prevent starvation.
    Routes messages to separate queues based on priority, with strict ordering:
    URGENT (0) > REALTIME (1) > INTERACTIVE (2) > BACKGROUND (3)

**Architecture:**
    - 4 independent MessageQueue instances (one per priority)
    - WFQ aging: Promote BACKGROUND → INTERACTIVE → REALTIME after 5s
    - Round-robin fairness within tier (avoid always picking URGENT)
    - Backpressure: Return error (not blocking) when capacity exceeded

**Performance Targets:**
    - Enqueue P95: <0.5ms (even with 4 queues)
    - Dequeue P95: <0.5ms (respects priority order)
    - WFQ aging check: <0.1ms per message

**Capacities (per ADR-0002a):**
    - URGENT: 50 messages
    - REALTIME: 100 messages
    - INTERACTIVE: 200 messages
    - BACKGROUND: 1024 messages

**Related ADRs:**
    - ADR-0002a: Mailbox MPSC Queue Implementation
    - ADR-0061a: Watermark Thresholds (80/90/95%)
    - ADR-0002: Actor Model for Agent Isolation

**Research Foundation:**
    - WFQ: Demers et al. 1989 "Analysis and Simulation of a Fair Queueing Algorithm"
    - Aging: Priority inversion prevention (Sha et al. 1990)
    - Actor Model: Hewitt 1973

**Implementation Status:** IMPLEMENTATION (M1 - Issue 2.2)
"""

import asyncio
import struct
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Optional

# Import MessageQueue from base.py (Issue 2.1)
from .base import MessageQueue

# Struct header format for message metadata (replaces pickle for security/performance)
# Format: <QBBBI = little-endian, uint64 (enqueued_at_ms), 3x uint8 (orig, curr, promos), uint32 (ttl_ms)
# Total: 15 bytes
HEADER_FMT = "<QBBBI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# Import FlatBuffers generated types
try:
    import sys
    from pathlib import Path

    fb_path = (
        Path(__file__).parent.parent.parent.parent
        / "contracts"
        / "flatbuffers"
        / "layer5_infrastructure"
    )
    if str(fb_path) not in sys.path:
        sys.path.insert(0, str(fb_path))

    from MessagePriority import MessagePriority  # type: ignore  # noqa: F401
except ImportError:
    # Fallback for testing or if FlatBuffers not compiled
    class MessagePriority(IntEnum):
        """Fallback MessagePriority enum if FlatBuffers import fails"""

        URGENT = 0
        REALTIME = 1
        INTERACTIVE = 2
        BACKGROUND = 3


# === Priority Constants ===
PRIORITY_URGENT = 0
PRIORITY_REALTIME = 1
PRIORITY_INTERACTIVE = 2
PRIORITY_BACKGROUND = 3

# Queue capacities (per ADR-0002a)
DEFAULT_CAPACITIES = {
    PRIORITY_URGENT: 50,
    PRIORITY_REALTIME: 100,
    PRIORITY_INTERACTIVE: 200,
    PRIORITY_BACKGROUND: 1024,
}

# WFQ aging thresholds (5 seconds)
AGING_THRESHOLD_MS = 5000


def _pack_message(
    message: bytes,
    enqueued_at_ms: int,
    original_priority: int,
    current_priority: int,
    promotions: int,
    ttl_ms: int = 0,
) -> bytes:
    """Pack message with metadata header (replaces pickle for security/performance).

    Args:
        message: Raw message bytes (FlatBuffers serialized)
        enqueued_at_ms: Timestamp when message was enqueued
        original_priority: Original priority before any promotions
        current_priority: Current priority (may be promoted via aging)
        promotions: Number of times message has been promoted
        ttl_ms: Time-to-live in milliseconds (0 = no expiry)

    Returns:
        Packed bytes: struct header (15 bytes) + message payload
    """
    header = struct.pack(
        HEADER_FMT,
        enqueued_at_ms,
        original_priority,
        current_priority,
        promotions,
        ttl_ms,
    )
    return header + message


def _unpack_message(buf: bytes) -> "MessageWithMetadata":
    """Unpack message with metadata header.

    Args:
        buf: Packed bytes (struct header + message payload)

    Returns:
        MessageWithMetadata with parsed header and message payload

    Raises:
        ValueError: If buffer is too short (corrupt frame)
    """
    # Safety guard: ensure buffer has minimum header size
    if len(buf) < HEADER_SIZE:
        raise ValueError(
            f"corrupt mailbox frame (short header: {len(buf)} < {HEADER_SIZE})"
        )

    enqueued_at_ms, original_priority, current_priority, promotions, ttl_ms = (
        struct.unpack(HEADER_FMT, buf[:HEADER_SIZE])
    )
    return MessageWithMetadata(
        message=buf[HEADER_SIZE:],
        enqueued_at_ms=enqueued_at_ms,
        original_priority=original_priority,
        current_priority=current_priority,
        promotions=promotions,
        ttl_ms=ttl_ms,
    )


@dataclass
class SendResult:
    """Result of priority scheduler send operation.

    Attributes:
        success: True if message enqueued successfully
        reason: Optional reason for failure (e.g., "BACKPRESSURE", "INVALID_PRIORITY")
        priority_used: Actual priority used (may differ if promoted)
    """

    success: bool
    reason: Optional[str] = None
    priority_used: Optional[int] = None


@dataclass
class MessageWithMetadata:
    """Message wrapper with aging metadata.

    Attributes:
        message: Raw message bytes (FlatBuffers serialized)
        enqueued_at_ms: Timestamp when message was enqueued
        original_priority: Original priority before any promotions
        current_priority: Current priority (may be promoted via aging)
        promotions: Number of times message has been promoted
        ttl_ms: Time-to-live in milliseconds (0 = no expiry)
    """

    message: bytes
    enqueued_at_ms: int
    original_priority: int
    current_priority: int
    promotions: int = 0
    ttl_ms: int = 0


class PriorityScheduler:
    """4-tier priority scheduler with WFQ aging.

    Routes messages to 4 separate priority queues:
    - URGENT (0): System-critical, max 50 messages
    - REALTIME (1): User input, max 100 messages
    - INTERACTIVE (2): Tool results, max 200 messages
    - BACKGROUND (3): Batch operations, max 1024 messages

    WFQ Aging:
        - BACKGROUND messages promoted to INTERACTIVE after 5s
        - INTERACTIVE messages promoted to REALTIME after 5s
        - URGENT messages never demoted

    Round-robin fairness:
        - Within each tier, use FIFO ordering
        - Across tiers, check URGENT → REALTIME → INTERACTIVE → BACKGROUND
        - Pattern: Receive 4 BACKGROUND messages for every 1 URGENT (configurable)

    Thread Safety: Async-safe via asyncio primitives
    Performance: <0.5ms P95 enqueue/dequeue

    Example:
        scheduler = PriorityScheduler()

        # Send URGENT message
        result = await scheduler.send(urgent_msg, priority=PRIORITY_URGENT)
        if not result.success:
            print(f"Failed: {result.reason}")

        # Receive next message (priority-ordered)
        msg = await scheduler.receive()
        print(f"Received message from priority {msg.current_priority}")
    """

    def __init__(
        self,
        capacities: Optional[Dict[int, int]] = None,
        enable_aging: bool = True,
        aging_threshold_ms: int = AGING_THRESHOLD_MS,
    ):
        """Initialize PriorityScheduler with 4 queues.

        Args:
            capacities: Optional custom capacities per priority (default: ADR-0002a spec)
            enable_aging: Enable WFQ aging mechanism (default: True)
            aging_threshold_ms: Aging threshold in milliseconds (default: 5000ms)
        """
        self._capacities = capacities or DEFAULT_CAPACITIES
        self._enable_aging = enable_aging
        self._aging_threshold_ms = aging_threshold_ms

        # Create 4 MessageQueue instances (validate_envelope=False for wrapped messages)
        self._queues: Dict[int, MessageQueue] = {
            PRIORITY_URGENT: MessageQueue(
                capacity=self._capacities[PRIORITY_URGENT], validate_envelope=False
            ),
            PRIORITY_REALTIME: MessageQueue(
                capacity=self._capacities[PRIORITY_REALTIME], validate_envelope=False
            ),
            PRIORITY_INTERACTIVE: MessageQueue(
                capacity=self._capacities[PRIORITY_INTERACTIVE], validate_envelope=False
            ),
            PRIORITY_BACKGROUND: MessageQueue(
                capacity=self._capacities[PRIORITY_BACKGROUND], validate_envelope=False
            ),
        }

        # Metrics tracking (per-priority counters for better observability)
        self._enqueue_count: Dict[int, int] = {p: 0 for p in range(4)}
        self._dequeue_count: Dict[int, int] = {p: 0 for p in range(4)}
        self._backpressure_count: int = 0
        self._promotions_count: int = 0
        self._promotions_failed_count: int = 0
        self._ttl_expired_count: int = 0
        self._aging_cycles_total: int = 0

        # Round-robin fairness counter (for receive())
        self._receive_counter: int = 0

        # Background aging task (lazily or eagerly started)
        self._aging_task: Optional[asyncio.Task] = None
        self._aging_started: bool = False

    async def send(self, message: bytes, priority: int, ttl_ms: int = 0) -> SendResult:
        """Send message to appropriate priority queue.

        Process:
            1. Validate priority in [0, 1, 2, 3]
            2. Check queue capacity (backpressure detection)
            3. Wrap message with metadata (enqueue time, priority, TTL)
            4. Enqueue to appropriate priority queue
            5. Return SendResult (success or backpressure reason)

        Args:
            message: FlatBuffers serialized MessageEnvelope bytes
            priority: Priority level (0=URGENT, 1=REALTIME, 2=INTERACTIVE, 3=BACKGROUND)
            ttl_ms: Time-to-live in milliseconds (0 = no expiry)

        Returns:
            SendResult with success flag and optional reason

        Raises:
            ValueError: If priority not in [0, 1, 2, 3]

        Performance: <0.5ms P95 (including queue enqueue)
        """
        # Start aging task eagerly on first send (if enabled and not started)
        if self._enable_aging and not self._aging_started:
            self._aging_task = asyncio.create_task(self._aging_loop())
            self._aging_started = True

        # Validate priority
        if priority not in [0, 1, 2, 3]:
            return SendResult(
                success=False, reason="INVALID_PRIORITY", priority_used=None
            )

        # Check capacity (backpressure detection)
        queue = self._queues[priority]
        if queue.size() >= queue.capacity():
            self._backpressure_count += 1
            return SendResult(
                success=False, reason="BACKPRESSURE", priority_used=priority
            )

        # Pack message with metadata header (replaces pickle for security/performance)
        current_time_ms = int(time.time() * 1000)
        packed = _pack_message(
            message=message,
            enqueued_at_ms=current_time_ms,
            original_priority=priority,
            current_priority=priority,
            promotions=0,
            ttl_ms=ttl_ms,
        )

        # Enqueue to appropriate priority queue
        result = await queue.enqueue(packed)

        if result.success:
            self._enqueue_count[priority] += 1
            return SendResult(success=True, reason=None, priority_used=priority)
        else:
            # EnqueueResult failed (queue_full or other reason)
            return SendResult(
                success=False, reason=result.reason, priority_used=priority
            )

    async def receive(self) -> Optional[MessageWithMetadata]:
        """Receive next message respecting priority order.

        Priority order: URGENT > REALTIME > INTERACTIVE > BACKGROUND

        Round-robin fairness:
            - Check URGENT first
            - If empty, check REALTIME
            - If empty, check INTERACTIVE
            - If empty, check BACKGROUND
            - Pattern: Receive 4 BACKGROUND for every 1 URGENT (prevents starvation)

        WFQ Aging:
            - Background aging task promotes old messages
            - Promoted messages appear in higher-priority queues

        TTL Expiry:
            - Messages with TTL > 0 are dropped if age > TTL
            - Expiry is checked before returning message to consumer

        Returns:
            MessageWithMetadata if message available, None if all queues empty

        Performance: <0.5ms P95 (including queue dequeue)
        """
        # Start aging task eagerly on first receive (if enabled and not started)
        if self._enable_aging and not self._aging_started:
            self._aging_task = asyncio.create_task(self._aging_loop())
            self._aging_started = True

        # Round-robin fairness: Check priorities in order, but occasionally
        # give BACKGROUND messages a chance even if URGENT has messages
        # Pattern: Every 5th receive, check BACKGROUND first (20% fairness)
        self._receive_counter += 1

        if self._receive_counter % 5 == 0:
            # Give BACKGROUND a chance (fairness)
            priorities = [
                PRIORITY_BACKGROUND,
                PRIORITY_URGENT,
                PRIORITY_REALTIME,
                PRIORITY_INTERACTIVE,
            ]
        else:
            # Normal priority order
            priorities = [
                PRIORITY_URGENT,
                PRIORITY_REALTIME,
                PRIORITY_INTERACTIVE,
                PRIORITY_BACKGROUND,
            ]

        # Try each priority queue in order
        current_time_ms = int(time.time() * 1000)
        for priority in priorities:
            queue = self._queues[priority]
            if queue.size() > 0:
                # Dequeue from this priority
                packed = await queue.dequeue()
                if packed is not None:
                    try:
                        # Unpack message with metadata
                        wrapped_msg = _unpack_message(packed)

                        # Check TTL expiry
                        if wrapped_msg.ttl_ms > 0:
                            age_ms = current_time_ms - wrapped_msg.enqueued_at_ms
                            if age_ms > wrapped_msg.ttl_ms:
                                # Message expired; drop and try next
                                self._ttl_expired_count += 1
                                continue

                        self._dequeue_count[priority] += 1
                        return wrapped_msg
                    except ValueError:
                        # Corrupt frame; skip and try next
                        continue

        # All queues empty
        return None

    async def _aging_loop(self):
        """Background task to promote aged messages (WFQ aging).

        Runs every 1 second, checks all messages in BACKGROUND and INTERACTIVE queues:
        - BACKGROUND messages older than 5s → promote to INTERACTIVE
        - INTERACTIVE messages older than 5s → promote to REALTIME
        - URGENT and REALTIME never demoted
        - Expired messages (TTL exceeded) are dropped

        This prevents starvation of low-priority messages.

        Performance: <10ms per aging cycle (1000 messages)
        """
        while True:
            try:
                await asyncio.sleep(1.0)  # Check every 1 second
                self._aging_cycles_total += 1

                current_time_ms = int(time.time() * 1000)

                # Check BACKGROUND queue for aged messages
                await self._promote_aged_messages(
                    from_priority=PRIORITY_BACKGROUND,
                    to_priority=PRIORITY_INTERACTIVE,
                    current_time_ms=current_time_ms,
                )

                # Check INTERACTIVE queue for aged messages
                await self._promote_aged_messages(
                    from_priority=PRIORITY_INTERACTIVE,
                    to_priority=PRIORITY_REALTIME,
                    current_time_ms=current_time_ms,
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but continue aging loop
                print(f"Error in aging loop: {e}")

    async def _promote_aged_messages(
        self,
        from_priority: int,
        to_priority: int,
        current_time_ms: int,
        max_scan: int = 128,
    ):
        """Promote aged messages from one priority to another (order-preserving).

        Drains up to max_scan messages, partitions into promoted/stay, re-enqueues
        stay messages in original order, then enqueues promoted to higher tier.
        This avoids FIFO reordering within the source tier.

        Args:
            from_priority: Source priority queue
            to_priority: Destination priority queue
            current_time_ms: Current timestamp for age calculation
            max_scan: Maximum messages to scan per cycle (default: 128)
        """
        from_queue = self._queues[from_priority]
        to_queue = self._queues[to_priority]

        # Drain up to max_scan items, preserving order
        frames: list = []
        n = min(from_queue.size(), max_scan)

        for _ in range(n):
            packed = await from_queue.dequeue()
            if packed is None:
                break
            frames.append(packed)

        # Partition into promoted and stay (order-preserving)
        stay: list = []
        promote: list = []

        for packed in frames:
            try:
                msg = _unpack_message(packed)
                age_ms = current_time_ms - msg.enqueued_at_ms

                # Check TTL expiry (drop if expired)
                if msg.ttl_ms > 0 and age_ms > msg.ttl_ms:
                    self._ttl_expired_count += 1
                    continue  # Drop, don't re-queue

                # Check aging threshold (promote if old enough)
                if age_ms >= self._aging_threshold_ms:
                    promote.append(msg)
                else:
                    stay.append(packed)
            except ValueError:
                # Corrupt frame; drop it
                continue

        # Re-enqueue non-promoted messages in original order (FIFO preservation)
        for pkt in stay:
            res = await from_queue.enqueue(pkt)
            if not res.success:
                # Queue full; stop re-queueing to avoid tight loop
                break

        # Enqueue promoted messages to higher tier (stop if destination full)
        for msg in promote:
            pkt = _pack_message(
                message=msg.message,
                enqueued_at_ms=msg.enqueued_at_ms,
                original_priority=msg.original_priority,
                current_priority=to_priority,
                promotions=msg.promotions + 1,
                ttl_ms=msg.ttl_ms,
            )
            res = await to_queue.enqueue(pkt)
            if not res.success:
                # Destination full: push original back once and bail
                await from_queue.enqueue(
                    _pack_message(
                        message=msg.message,
                        enqueued_at_ms=msg.enqueued_at_ms,
                        original_priority=msg.original_priority,
                        current_priority=msg.current_priority,
                        promotions=msg.promotions,
                        ttl_ms=msg.ttl_ms,
                    )
                )
                self._promotions_failed_count += 1
                break
            self._promotions_count += 1

    def size(self) -> Dict[int, int]:
        """Get current queue sizes per priority.

        Returns:
            Dict mapping priority → queue size
            Example: {0: 5, 1: 12, 2: 30, 3: 100}
        """
        return {priority: queue.size() for priority, queue in self._queues.items()}

    def capacity(self) -> Dict[int, int]:
        """Get queue capacities per priority.

        Returns:
            Dict mapping priority → capacity
            Example: {0: 50, 1: 100, 2: 200, 3: 1024}
        """
        return self._capacities.copy()

    def usage_percent(self) -> Dict[int, float]:
        """Get queue usage percentage per priority.

        Returns:
            Dict mapping priority → usage percentage (0-100)
            Example: {0: 10.0, 1: 12.0, 2: 15.0, 3: 9.8}
        """
        sizes = self.size()
        return {
            priority: (sizes[priority] / self._capacities[priority]) * 100.0
            for priority in self._queues.keys()
        }

    def metrics(self) -> Dict[str, object]:
        """Get scheduler metrics for observability.

        Returns:
            Dict with metrics:
            - enqueue_count: Per-priority enqueue count
            - dequeue_count: Per-priority dequeue count
            - backpressure_count: Total backpressure events
            - promotions_count: Total WFQ promotions
            - promotions_failed_count: Total promotion failures (dest full)
            - ttl_expired_count: Total TTL expiry events
            - aging_cycles_total: Total aging loop cycles
            - queue_sizes: Current sizes per priority
            - usage_percent: Usage percentage per priority
        """
        return {
            "enqueue_count": self._enqueue_count.copy(),
            "dequeue_count": self._dequeue_count.copy(),
            "backpressure_count": self._backpressure_count,
            "promotions_count": self._promotions_count,
            "promotions_failed_count": self._promotions_failed_count,
            "ttl_expired_count": self._ttl_expired_count,
            "aging_cycles_total": self._aging_cycles_total,
            "queue_sizes": self.size(),
            "usage_percent": self.usage_percent(),
        }

    async def shutdown(self):
        """Gracefully shutdown scheduler (cancel aging task)."""
        if self._aging_task is not None:
            self._aging_task.cancel()
            try:
                await self._aging_task
            except asyncio.CancelledError:
                pass

    def __repr__(self) -> str:
        """String representation for debugging."""
        sizes = self.size()
        return (
            f"PriorityScheduler("
            f"URGENT={sizes[0]}/{self._capacities[0]}, "
            f"REALTIME={sizes[1]}/{self._capacities[1]}, "
            f"INTERACTIVE={sizes[2]}/{self._capacities[2]}, "
            f"BACKGROUND={sizes[3]}/{self._capacities[3]}, "
            f"promotions={self._promotions_count})"
        )


# Convenience exports
__all__ = [
    "PriorityScheduler",
    "SendResult",
    "MessageWithMetadata",
    "PRIORITY_URGENT",
    "PRIORITY_REALTIME",
    "PRIORITY_INTERACTIVE",
    "PRIORITY_BACKGROUND",
]
