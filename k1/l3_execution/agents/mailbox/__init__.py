"""
K1 Layer 3 Execution — agents/mailbox/

PURPOSE:
========
Inter-agent messaging implementation using MPSC (Multi-Producer Single-Consumer) queues.
Provides <1ms enqueue/dequeue with 4-tier priority and backpressure handling.

RESPONSIBILITIES:
=================
1. MPSC Queue: Ring buffer, 4-tier priority (URGENT/REALTIME/INTERACTIVE/BACKGROUND)
2. Backpressure: High watermark (50), low watermark (25), overflow policies (DROP_OLDEST)
3. Dead Letter Queue: 100 messages, 5 min retention, dropped reasons
4. WFQ Scheduling: Weight-based fairness (URGENT 10×, BACKGROUND 1×)

PRIMARY ADRs:
=============
- ADR-0002a: Actor Fabric Mailbox (MPSC queue, 4-tier priority)
  * Lock-free MPSC queue (ring buffer implementation)
  * 4 priority tiers: URGENT (10× weight), REALTIME (5× weight), INTERACTIVE (2× weight), BACKGROUND (1× weight)
  * Backpressure handling: high watermark 50, low watermark 25
  * Overflow policies: DROP_OLDEST, DROP_NEWEST, REJECT

- ADR-0028: WFQ Scheduler (priority-based scheduling)
  * Weighted Fair Queueing for message dequeue
  * Virtual time advancement: vtime += message_size / queue_weight
  * Prevents starvation: BACKGROUND messages processed even with URGENT backlog

RELATED ADRs:
=============
- ADR-0024: Performance Budgets (mailbox <1ms)
- ADR-0029: Prometheus Metrics (mailbox depth, message rate)

MAILBOX ARCHITECTURE:
=====================
**4-Tier Priority Queue:**
```
┌─────────────────────────────────────┐
│  URGENT (weight=10)                 │  ← Supervisor heartbeats, barge-in
├─────────────────────────────────────┤
│  REALTIME (weight=5)                │  ← Turn execution, tool calls
├─────────────────────────────────────┤
│  INTERACTIVE (weight=2)             │  ← User messages, agent responses
├─────────────────────────────────────┤
│  BACKGROUND (weight=1)              │  ← Metrics, cleanup, housekeeping
└─────────────────────────────────────┘
```

**Ring Buffer (Lock-Free):**
- Capacity: 100 messages (configurable)
- Head pointer: Read index (atomic)
- Tail pointer: Write index (atomic)
- Lock-free: CAS (Compare-And-Swap) operations

**WFQ Scheduling:**
```python
class WFQScheduler:
    def __init__(self):
        self.virtual_time = 0.0
        self.queue_weights = {
            Priority.URGENT: 10.0,
            Priority.REALTIME: 5.0,
            Priority.INTERACTIVE: 2.0,
            Priority.BACKGROUND: 1.0
        }

    def dequeue_next(self) -> Message:
        \"\"\"Dequeue message with lowest virtual finish time.\"\"\"
        min_vtime = float('inf')
        selected_queue = None

        for priority, queue in self.queues.items():
            if not queue.empty():
                # Calculate virtual finish time
                vtime = queue.virtual_start_time + (1.0 / self.queue_weights[priority])
                if vtime < min_vtime:
                    min_vtime = vtime
                    selected_queue = (priority, queue)

        if selected_queue:
            priority, queue = selected_queue
            message = queue.dequeue()
            queue.virtual_start_time = min_vtime
            return message
        return None
```

BACKPRESSURE HANDLING:
======================
**Watermarks:**
- **High watermark:** 50 messages (trigger backpressure)
- **Low watermark:** 25 messages (clear backpressure)
- **Overflow policy:** DROP_OLDEST (default), DROP_NEWEST, REJECT

**Overflow Handling:**
```python
async def enqueue(self, message: Message, priority: Priority) -> bool:
    \"\"\"Enqueue message with backpressure handling.\"\"\"
    queue = self.queues[priority]

    if queue.size() >= HIGH_WATERMARK:
        # Backpressure triggered
        if self.overflow_policy == OverflowPolicy.DROP_OLDEST:
            queue.dequeue()  # Drop oldest message
            self.dead_letter_queue.add(message, reason="overflow")
        elif self.overflow_policy == OverflowPolicy.DROP_NEWEST:
            self.dead_letter_queue.add(message, reason="overflow")
            return False  # Reject new message
        elif self.overflow_policy == OverflowPolicy.REJECT:
            return False  # Reject new message

    queue.enqueue(message)
    return True
```

DEAD LETTER QUEUE:
==================
- **Capacity:** 100 messages
- **Retention:** 5 min (auto-expire old messages)
- **Reasons:** overflow, timeout, invalid_message, agent_terminated

```python
class DeadLetterQueue:
    def __init__(self):
        self.messages = []  # List[(message, reason, timestamp)]
        self.max_size = 100
        self.retention_ms = 300_000  # 5 min

    def add(self, message: Message, reason: str) -> None:
        \"\"\"Add message to DLQ.\"\"\"
        now = time.monotonic() * 1000
        self.messages.append((message, reason, now))

        # Evict expired messages
        self.messages = [
            (msg, r, ts) for (msg, r, ts) in self.messages
            if now - ts < self.retention_ms
        ]

        # Enforce max size
        if len(self.messages) > self.max_size:
            self.messages = self.messages[-self.max_size:]
```

PERFORMANCE METRICS:
====================
- Enqueue: <1ms P95 (lock-free CAS)
- Dequeue: <0.5ms P95 (WFQ scheduling)
- Mailbox depth: <10 typical, <50 high watermark
- Message throughput: 1000+ msgs/sec per mailbox

INTEGRATION POINTS:
===================
**Send Message (Producer):**
```python
from k1.l3_execution.agents.mailbox import Mailbox, Priority

mailbox = Mailbox(agent_id="agent_123")
await mailbox.enqueue(
    message=TaskAssignment(task_id, step_def),
    priority=Priority.REALTIME
)
```

**Receive Message (Consumer):**
```python
# Agent event loop
while agent.state == State.ACTIVE:
    message = await mailbox.dequeue(timeout_ms=1000)
    if message:
        await process_message(message)
```

TESTING:
========
See tests/l3_execution/agents/test_mailbox.py (ADR-0004d):
- Enqueue/dequeue performance (<1ms)
- 4-tier priority scheduling
- WFQ fairness (URGENT vs BACKGROUND)
- Backpressure handling (overflow policies)
- Dead letter queue (retention, expiration)
- Lock-free correctness (concurrent producers)

OBSERVABILITY:
==============
Prometheus Metrics (ADR-0029):
- layer3_mailbox_depth{agent_id, priority}
- layer3_mailbox_enqueue_rate{agent_id, priority}
- layer3_mailbox_dequeue_rate{agent_id}
- layer3_mailbox_overflow_total{agent_id, policy}
- layer3_dead_letter_queue_size{agent_id}

Structured Logs:
```python
logger.warning(
    "mailbox_overflow",
    agent_id=agent_id,
    priority=priority,
    mailbox_depth=depth,
    overflow_policy=policy,
    trace_id=trace_id
)
```

RESEARCH FOUNDATIONS:
=====================
- Actor Model Mailboxes (Hewitt 1973) — Message passing
- Weighted Fair Queueing (Demers et al. 1990) — Fair scheduling
- Lock-Free Queues (Michael & Scott 1996) — Concurrent data structures

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
