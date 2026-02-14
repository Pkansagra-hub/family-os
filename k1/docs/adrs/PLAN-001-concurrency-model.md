---
adr_id: PLAN-001
title: "Planner Concurrency Model -- V1 Single-Plan asyncio.Lock"
status: Accepted
date: 2026-02-14
module: planner
layer: "L3"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-002"
  - "ORCH-005"
  - "PLAN-003"
  - "PLAN-004"
related_events:
  - "k1.planner.plan.request.v1"
  - "k1.planner.plan.cancel.v1"
  - "k1.planner.plan.ready.v1"
  - "k1.planner.plan.failed.v1"
  - "k1.planner.plan.cancelled.v1"
related_contracts:
  - "k1/contracts/modules/planner/wiring.contract.yaml"
  - "k1/contracts/modules/planner/module.contract.yaml"
related_ports:
  - "IMailboxPort"
implements_issue: "1.1.3"
superseded_by: ""
tags:
  - concurrency
  - planner
  - asyncio
  - mailbox
  - single-plan
---

# PLAN-001: Planner Concurrency Model -- V1 Single-Plan asyncio.Lock

## Context

### Problem Statement

The Planner module must handle concurrent plan requests from the Orchestrator while maintaining predictable resource usage and avoiding race conditions. A full planning pipeline (SKETCH -> EXPAND -> VALIDATE -> COMMIT) takes ~12s P50 and involves LLM calls, discovery tool calls, and event emissions. The concurrency model must ensure correctness without excessive complexity.

### Current Situation

planner.md SS24 defines the concurrency model. The Planner runs as a single-threaded async actor within the K1 event loop. Multiple plan requests can arrive via the Orchestrator's `PlannerAdapter`, but only one plan can execute at a time due to LLM resource constraints and state management simplicity.

### Constraints

- Single Python event loop (no thread pool, no multiprocessing)
- LLM calls are expensive and sequential per plan (~12s P50 total)
- V1 does not require multi-plan concurrency (V2 consideration)
- Must not block the Orchestrator's mailbox loop (async protocol via events)
- Micro-replan requests must be serviceable during idle periods

### Requirements

- At most 1 active plan at any time (V1)
- Requests queued when a plan is in flight
- Queue bounded to prevent unbounded memory growth
- Clean cancellation between stages
- Micro-replan must acquire the same lock

---

## Decision

### Chosen Approach

V1 uses single-plan concurrency via `asyncio.Lock` (planner.md SS24.1).

### Key Design

**Lock Mechanism:**
- `PlannerAgent._plan_lock: asyncio.Lock` -- acquired at PLAN_START step 3 (SS23.2), released at PLAN_END step 2 (SS23.4)
- FIFO ordering for lock waiters (SS24.1.1) -- guaranteed by asyncio.Lock semantics
- Lock is non-reentrant -- a plan in flight blocks all other plan attempts

**Mailbox Queue:**
- `MailboxAdapter._queue: asyncio.Queue(maxsize=5)` -- depth-5 FIFO queue (SS4.1)
- INTERACTIVE priority only (V1 does not implement Weighted Fair Queuing)
- When queue is full: `enqueue()` returns `PlanAck(status=REJECTED)` immediately
- When queue has space: `enqueue()` returns `PlanAck(status=ACCEPTED)` and appends to queue

**Request Processing Loop:**
```
async def _process_loop(self):
    while self._running:
        request = await self._mailbox.dequeue()  # blocks until request available
        if request.request_id in self._cancel_set:
            emit plan.cancelled.v1
            continue
        async with self._plan_lock:
            await self._pipeline.execute(request)
```

**Cooperative Cancellation:**
- Cancel requests add `request_id` to `_cancel_set: Set[str]`
- Checked at 5 points (SS24.2.2): pre-dequeue, between each stage pair, before WAL persist
- No preemption -- cancel flag is checked cooperatively between stages
- If plan already in COMMIT, cancel is too late (plan completes)

**Micro-Replan Concurrency:**
- `micro_replan()` acquires `_plan_lock` (SS24.3)
- If a full plan is in flight, `micro_replan()` awaits the lock
- Caller-side timeout is 10s -- since a full plan takes ~12s P50, micro-replan almost always times out during active plan
- Returns `None` on timeout (Orchestrator falls back to original plan)
- Does NOT use the mailbox queue -- bypasses queue entirely (SS4.2)

### Rationale

Single-plan concurrency is the simplest correct model for V1:
- Avoids all race conditions on shared state (FSM, token counters, tool budget)
- Avoids LLM resource contention (one set of LLM calls at a time)
- Bounded queue prevents memory growth from request storms
- asyncio.Lock is native, zero-dependency, well-tested

---

## Alternatives Considered

### Alternative 1: Thread Pool for Concurrent Plans

**Description:** Dispatch each plan to a thread pool worker, allowing 2-3 concurrent plans.

**Pros:**
- Higher throughput under load

**Cons:**
- GIL limits true parallelism for CPU-bound validation
- Race conditions on shared state require explicit synchronization
- LLM calls are I/O-bound but Model Hub has its own concurrency limits

**Rejected because:** Complexity outweighs benefits for V1 workload (typically 1 plan at a time). Deferred to V2 (SS24.4).

### Alternative 2: No Queue (Reject All When Busy)

**Description:** Reject any plan request that arrives while a plan is in flight. No queuing.

**Pros:**
- Simplest possible model

**Cons:**
- Orchestrator must implement retry logic
- Bursts of requests all get rejected
- No fairness -- first-come-first-served without queue

**Rejected because:** Depth-5 queue absorbs normal burst patterns (Orchestrator may send 2-3 requests in rapid succession during multi-task handling). Cost is minimal (5 PlanRequest objects ~25KB total).

---

## Consequences

### Positive

- Zero race conditions in V1 (single writer to all plan state)
- Predictable resource usage (1 LLM call sequence at a time)
- Simple reasoning about plan lifecycle (exactly one FSM active)
- asyncio.Lock has no external dependencies

### Negative

- Throughput limited to 1 plan per ~12s (P50)
- Micro-replan during active plan almost always times out
- Queue depth 5 may need tuning under production load

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Queue overflow under burst | Low | Low | PlanAck(REJECTED) is graceful; Orchestrator retries |
| Lock starvation (long plan holds lock) | Low | Med | 45s pipeline timeout (PLAN-04) guarantees lock release |
| Micro-replan always timing out | Med | Low | V2 may implement SKETCH preemption (SS24.4) |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| PlannerAgent | `k1/planner/planner_agent.py` [F02] | New -- _plan_lock, _cancel_set, _process_loop |
| MailboxAdapter | `k1/planner/adapters/mailbox_adapter.py` [F28] | New -- depth-5 asyncio.Queue |
| PipelineController | `k1/planner/pipeline_controller.py` [F03] | New -- cancel_check callback |
| PlannerConfig | `k1/planner/config.py` [F07] | New -- mailbox_depth=5, pipeline_timeout_ms=45000 |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
|-------------|-----------|-------------|
| `k1.planner.plan.request.v1` | Consumed | Incoming plan request from Orchestrator |
| `k1.planner.plan.cancel.v1` | Consumed | Cancel request for in-flight or queued plan |
| `k1.planner.plan.ready.v1` | Emitted | Plan completed successfully |
| `k1.planner.plan.failed.v1` | Emitted | Plan failed (all recovery paths exhausted) |
| `k1.planner.plan.cancelled.v1` | Emitted | Plan cancelled via cooperative check |

### Contracts Affected

| Contract | Type | Change |
|----------|------|--------|
| `wiring.contract.yaml` | Module Wiring | Defines IMailboxPort as required port |
| `module.contract.yaml` | Module | Declares concurrency=single-plan |

### Port/Adapter Impact

| Port | Adapter | Change |
|------|---------|--------|
| `IMailboxPort` | `MailboxAdapter` | New -- depth-5 queue, enqueue/dequeue/send_cancel |

### Success Metrics

- Lock contention rate: < 5% of requests wait on lock (burst absorption by queue)
- Queue rejection rate: < 1% of requests rejected (queue full)
- Cancel latency: < 500ms from cancel request to plan.cancelled.v1 emission

### Testing Strategy

- [ ] Unit tests in `tests/k1/planner/` -- lock acquisition/release, queue depth, cancel protocol
- [ ] Integration tests -- concurrent enqueue + cancel, micro-replan lock contention
- [ ] Contract tests -- IMailboxPort Protocol compliance

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-14 | K1 Architecture Team | Initial decision -- V1 single-plan asyncio.Lock |
