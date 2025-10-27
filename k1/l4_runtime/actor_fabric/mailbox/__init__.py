"""
K1 L4 Runtime — Actor Mailbox (MPSC Queue with 4-Tier Priority)

**Purpose:** Multi-producer single-consumer queue with 4-tier priority, WFQ scheduling, backpressure, DLQ

**Mailbox Architecture:**
- MPSC Queue (multi-producer, single-consumer, lock-free ring buffer)
- 4-Tier Priority: URGENT > REALTIME > INTERACTIVE > BACKGROUND
- WFQ Scheduler (Weighted Fair Queuing) with aging to prevent starvation
- Backpressure (high watermark 50, low watermark 25)
- Dead Letter Queue (DLQ, 100 messages, 5-min retention)

**Performance:**
- Enqueue: <1ms P95 (lock-free ring buffer)
- Dequeue: <0.5ms P95 (WFQ scheduling)
- Capacity: 100 messages per actor (configurable)
- Backpressure trigger: 50 messages (high watermark)

**ADR:**
- ADR-0002a: Mailbox (MPSC queue, 4-tier priority, WFQ scheduler, backpressure, DLQ, TTL)

**Priority Tiers:**

1. **URGENT (P0):** Lifecycle events, crash signals, OOM prevention
   - Examples: DRAINING state, supervisor kill, session termination
   - WFQ weight: 50% (highest priority)

2. **REALTIME (P1):** User-facing real-time operations
   - Examples: Voice barge-in, user message, tool execution
   - WFQ weight: 30%

3. **INTERACTIVE (P2):** User-visible but not time-critical
   - Examples: Plan generation, context switch detection
   - WFQ weight: 15%

4. **BACKGROUND (P3):** Background tasks, telemetry, cleanup
   - Examples: Metrics export, eviction, WAL checkpoint
   - WFQ weight: 5%

**WFQ Scheduler (Weighted Fair Queuing):**

```python
class WFQScheduler:
    _queues: Dict[Priority, Deque[Message]] = {
        Priority.URGENT: deque(),
        Priority.REALTIME: deque(),
        Priority.INTERACTIVE: deque(),
        Priority.BACKGROUND: deque(),
    }
    _weights = {Priority.URGENT: 0.5, Priority.REALTIME: 0.3, Priority.INTERACTIVE: 0.15, Priority.BACKGROUND: 0.05}
    _virtual_time: float = 0.0  # Aging counter to prevent starvation

    async def dequeue() -> Message:
        # <0.5ms P95: WFQ scheduling with aging
        # Prevent starvation: increment virtual_time for each dequeue
```

**Aging Algorithm (Starvation Prevention):**
- Each message has `enqueue_time_ms` timestamp
- Virtual time increments on every dequeue
- If BACKGROUND queue age > 10s, temporarily boost to INTERACTIVE priority
- Ensures BACKGROUND messages eventually processed

**Backpressure (ADR-0002a):**

```python
# High Watermark: 50 messages
# Low Watermark: 25 messages

async def enqueue(message: Message) -> EnqueueResult:
    if len(mailbox) >= 50:  # High watermark
        if message.priority == Priority.URGENT:
            # URGENT always accepted, evict oldest BACKGROUND
            _drop_oldest_background()
            _mailbox.append(message)
            return EnqueueResult.ACCEPTED_WITH_DROP
        else:
            # Reject non-URGENT messages
            _dlq.append(message, reason="mailbox_full")
            return EnqueueResult.REJECTED_BACKPRESSURE
    else:
        _mailbox.append(message)
        return EnqueueResult.ACCEPTED
```

**Dead Letter Queue (DLQ):**
- Stores dropped messages for debugging and replay
- Capacity: 10000 messages (production-ready)
- Retention: 24 hours (configurable)
- O(1) lookup by dlq_id and trace_id (hash-indexed)
- Reasons: `OVERFLOW`, `TTL_EXPIRED`, `INVALID_SCHEMA`, `ACTOR_TERMINATED`
- Replay support: Mark messages for replay to new recipient
- Prometheus metrics: `mailbox_dlq_depth`, `mailbox_dlq_enqueued_total`, `mailbox_dlq_expired_total`

**TTL (Time-to-Live):**
- Each message has optional `ttl_ms` field
- Expired messages moved to DLQ before processing
- Default TTL: None (no expiration)
- Use case: Realtime messages (e.g., voice frames) with 500ms TTL

**Files:**
- base.py — Core MPSC queue implementation (Issue 2.1 ✅ COMPLETE)
- scheduler.py — WFQ scheduler with aging, priority queues (Issue 2.2 ✅ COMPLETE)
- backpressure.py — Watermark monitoring, overflow policies (TODO: Issue 2.3)
- dead_letter.py — Dead letter queue, dropped message storage, replay (Issue 2.6 ✅ COMPLETE)
- cleanup.py — TTL expiration tracking and cleanup task (Issue 2.4 ✅ COMPLETE)
- model/ — FlatBuffers generated code (MessageEnvelope, MessagePriority, MessageType)

**Integration:**
- Actor Fabric: Core message routing infrastructure
- Router: Admission control feeds into mailbox backpressure
- Supervisor: URGENT priority for lifecycle events
- L5 Thermal: Backpressure signals trigger admission control

**Performance Metrics:**
- actor_mailbox_enqueue_total (counter, priority, result=accepted|rejected)
- actor_mailbox_dequeue_total (counter, priority)
- actor_mailbox_size (gauge, per-actor, per-priority)
- actor_mailbox_enqueue_latency_ms (histogram)
- actor_mailbox_dequeue_latency_ms (histogram)
- actor_mailbox_dlq_total (counter, reason)
- actor_mailbox_aging_boosts_total (counter) — Starvation prevention activations

**Research Foundations:**
- Weighted Fair Queuing (Demers et al. 1989) — Fair scheduling
- MPSC Queue (Michael & Scott 1996) — Lock-free data structures

**Last Updated:** October 26, 2025
**Status:** Issue 2.1 COMPLETE ✅ - Base MPSC queue production-ready
          Issue 2.2 COMPLETE ✅ - Priority scheduler with WFQ aging
"""

__version__ = "0.2.0"

from .base import EnqueueResult, MessageQueue
from .dead_letter import DeadLetterQueue, DLQEntry
from .scheduler import (
    PRIORITY_BACKGROUND,
    PRIORITY_INTERACTIVE,
    PRIORITY_REALTIME,
    PRIORITY_URGENT,
    MessageWithMetadata,
    PriorityScheduler,
    SendResult,
)

__all__ = [
    "MessageQueue",
    "EnqueueResult",
    "PriorityScheduler",
    "SendResult",
    "MessageWithMetadata",
    "PRIORITY_URGENT",
    "PRIORITY_REALTIME",
    "PRIORITY_INTERACTIVE",
    "PRIORITY_BACKGROUND",
    "DeadLetterQueue",
    "DLQEntry",
]
