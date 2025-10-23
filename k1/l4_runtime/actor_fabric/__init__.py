"""
K1 L4 Runtime — Actor Fabric

**Purpose:** Actor Model implementation with mailbox, router, supervisor for K1 agent infrastructure

**Components:**
- mailbox/ — MPSC queue, 4-tier priority, WFQ scheduler, backpressure, DLQ
- router/ — Location transparency, routing table, 5-check admission control
- supervisor/ — Heartbeat monitoring (1Hz), crash detection (<100ms), blacklist

**Performance:**
- Mailbox enqueue: <1ms P95
- Mailbox dequeue: <0.5ms P95
- Router admission: <2ms P95 (5 checks)
- Crash detection: <100ms P95

**ADRs (7 total):**

**Actor Model & Fabric (3 ADRs):**
- ADR-0002: Actor Model (isolated actors, message passing, no shared memory, supervision trees)
- ADR-0002a: Mailbox (MPSC queue, 4-tier priority URGENT/REALTIME/INTERACTIVE/BACKGROUND, WFQ scheduler, DLQ)
- ADR-0002b: Supervisor (heartbeat 1Hz ping, 1.5s timeout, crash detection <2s, blacklist 3 crashes in 10min)
- ADR-0002c: Router (location transparency, routing table, 5-check admission: capability/role/token-bucket/in-flight/quota)

**Agent Lifecycle (4 ADRs):**
- ADR-0005: Lifecycle FSM (6-state PENDING/WARMING/ACTIVE/IDLE/DRAINING/TERMINATED)
- ADR-0005b: IDLE Pooling (TTL tracking 5min, reactivation <50ms P95, pool hit rate >80%)
- ADR-0005c: DRAINING State (3-phase drain: stop tasks/complete in-flight/cleanup, 5s timeout)
- ADR-0005d: Supervisor (heartbeat monitoring 1s interval, 3s timeout, event-loop heartbeat 200ms)
- ADR-0005e: Personalities (4 AI agents + 54 pure actors)

**Actor Model Architecture (ADR-0002):**

```python
class Actor:
    actor_id: str
    mailbox: Mailbox  # MPSC queue with 4-tier priority
    state: ActorState  # Private state, no shared memory
    supervisor: ActorRef  # Supervision tree reference

    async def receive(message: Message) -> None:
        # Message processing loop
        # Isolated execution, no shared state
```

**Hybrid Architecture:** 4 AI agents (Planner, Concierge, Researcher, Tool Executor) + 54 pure actors (deterministic FSMs)

**Research Foundations:**
- Hewitt (1973) — Actor Model (isolated actors, message passing)
- Armstrong (2003) — Erlang/OTP (supervision trees, let-it-crash)
- Agha (1986) — Actors: A Model of Concurrent Computation

**Integration:**
- L3 Execution: Agent hire/fire, mailbox routing
- SessionState: Agent leases, ACTIVE/IDLE state tracking
- Protocol Monitor: Message validation, FSM transitions
- L5 Thermal: Backpressure signals, admission control

**Performance Metrics:**
- actor_mailbox_enqueue_total (counter, priority=URGENT|REALTIME|INTERACTIVE|BACKGROUND)
- actor_mailbox_dequeue_total (counter)
- actor_mailbox_size (gauge, per-actor)
- actor_router_admission_checks_total (counter, result=allow|deny, reason)
- actor_supervisor_crashes_total (counter, actor_id)
- actor_supervisor_blacklist_total (counter, actor_id)

**Last Updated:** October 2025
**Status:** Production-ready Actor Fabric with supervision
"""

__version__ = "0.1.0"
