---
adr_id: ORCH-012
title: "Event-Driven Concurrency for HIGH Tier -- Non-Blocking Plan Acquisition"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-002"
  - "ORCH-005"
  - "ORCH-004"
related_events:
  - "k1.planner.plan.ready.v1"
  - "k1.orchestration.task.accepted.v1"
  - "k1.hil.fallback_response.v1"
  - "k1.hil.override_response.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
related_ports:
  - "IMailboxPort"
  - "IPlannerPort"
  - "IEventSubscriptionPort"
implements_issue: "1.1.12"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - concurrency
  - event-driven
  - high-tier
  - plan-acquisition
---

# ORCH-012: Event-Driven Concurrency for HIGH Tier -- Non-Blocking Plan Acquisition

## Context

### Problem Statement

HIGH tier tasks require a CommittedPlan from the Planner before DAG execution can begin. The Planner's 4-stage pipeline (Sketch, Expand, Validate, Commit) takes significant time. A naive `await_plan()` call would block the mailbox loop for the entire planning duration, preventing MEDIUM tier tasks, WorkflowRunRequests, and InterruptRequests from being processed.

This resolves ARCH-1 (await_plan blocking) from the implementation plan.

### Current Situation

ORCH-005 establishes the single-threaded mailbox loop. ORCH-002 defines the Planner protocol. The mailbox loop must remain responsive during HIGH tier planning to avoid head-of-line blocking.

### Constraints

- Mailbox loop is single-threaded (ORCH-005) -- cannot block on I/O
- Planner pipeline duration: unpredictable (LLM-dependent, up to 45s CB timeout)
- MEDIUM tier tasks must continue processing during HIGH tier planning
- InterruptRequests must be delivered even during active planning
- Multiple HIGH tier tasks may be pending plans simultaneously (V1: unlikely but must not corrupt state)

### Requirements

- dispatch_high() must return immediately (non-blocking)
- CommittedPlan arrival triggers DAG execution automatically
- Context from original TaskEnvelope must survive the planning gap
- Stale/abandoned plan requests must be reaped
- Same pattern must extend to HIL (Human-in-the-Loop) responses

---

## Decision

### Chosen Approach

**Event-driven context-parking model: dispatch_high() parks context, returns to mailbox loop. CommittedPlan arrives as mailbox message, triggers DAG execution.**

### Key Design

**Complete HIGH Tier Flow:**

```text
1. TaskEnvelope(HIGH) dequeued from mailbox
2. dispatch_high():
   a. Read SessionState snapshot (context for Planner)
   b. Build PlanRequest(request_id=uuid4(), intent, constraints, context)
   c. Park context: PendingPlanContext{request_id, envelope, snapshot, parked_at}
   d. Send PlanRequest to Planner via IPlannerPort.request_plan()
   e. Return ProcessResult.DEFERRED  -- mailbox loop continues

3. ... mailbox loop processes other messages (MEDIUM, workflows, interrupts) ...

4. Planner completes 4-stage pipeline
5. CommittedPlan published on k1.planner.plan.ready.v1
6. IEventSubscriptionPort receives event
7. Event adapter routes CommittedPlan to mailbox as internal message

8. CommittedPlan dequeued from mailbox
9. receive_plan():
   a. Extract request_id from CommittedPlan
   b. Lookup PendingPlanContext by request_id
   c. If found: retrieve parked envelope + snapshot
   d. If not found: log orphan plan, discard (stale/reaped)
   e. Execute DAG: DAGExecutor.execute(committed_plan, parked_context)
   f. Remove PendingPlanContext entry
   g. Aggregate results -> return to Concierge
```

**PendingPlanContext Store:**

```python
@dataclass
class PendingPlanContext:
    request_id: str              # Correlation key (echoed in CommittedPlan)
    envelope: TaskEnvelope       # Original task envelope
    snapshot: ContextSnapshot    # SessionState snapshot at park time
    parked_at: float             # Epoch time for timeout tracking
    timeout_ms: int = 45_000     # CB_PLANNER timeout

# Store: Dict[str, PendingPlanContext] -- keyed by request_id
# Accessed ONLY from mailbox loop (single-threaded, no locks needed)
```

**PendingHILContext Store (Same Pattern):**

```python
@dataclass
class PendingHILContext:
    correlation_id: str          # HIL request correlation
    dag_id: str                  # Active DAG that triggered HIL
    step_id: str                 # Step requiring human input
    constraint_type: str         # "FALLBACK" | "OVERRIDE"
    parked_at: float
    timeout_ms: int              # FALLBACK: 60s, OVERRIDE: 30s

# Store: Dict[str, PendingHILContext] -- keyed by correlation_id
# Used by ConstraintResolver (3.1.5) for HIL fallback
# Used by ExecutionMonitor for user override responses
```

**Timeout Reaper:**

```text
_reap_stale_contexts():
  Runs every 5 seconds (scheduled via mailbox loop tick)
  For each PendingPlanContext:
    if (now - parked_at) > timeout_ms:
      Remove from store
      Build AggregatedResult{success=false, error="PLAN_TIMEOUT"}
      Deliver to Concierge via normal result path
      Emit k1.orchestration.task.timeout.v1 delta

  For each PendingHILContext:
    if (now - parked_at) > timeout_ms:
      Remove from store
      Set interrupt flag on active DAG (graceful failure)
      Log timeout with trace_id
```

**Timeout Configuration:**

| Context Type | Timeout | Source |
|-------------|---------|--------|
| PendingPlanContext | 45s | CB_PLANNER timeout |
| PendingHILContext (FALLBACK) | 60s | HIL constraint fallback |
| PendingHILContext (OVERRIDE) | 30s | User override response |
| Reaper interval | 5s | Fixed (not configurable V1) |

**Concurrency Characteristics:**

| Scenario | Behavior |
|----------|----------|
| MEDIUM arrives during HIGH planning | Processed normally (mailbox loop is free) |
| InterruptRequest arrives during HIGH planning | Processed normally (no DAG active yet for HIGH -- interrupt targets active DAG if any) |
| WorkflowRunRequest arrives during HIGH planning | Processed normally |
| Second HIGH arrives during first HIGH planning | Second context parked alongside first (independent request_ids) |
| CommittedPlan arrives after timeout reap | Orphan plan detected (no matching PendingPlanContext), discarded with log |
| CommittedPlan arrives for unknown request_id | Discarded with warning log (possible stale event replay) |

**Mailbox Message Priority:**

CommittedPlan messages and HIL responses are routed to mailbox with REALTIME priority (per ORCH-004) to ensure they are processed before queued INTERACTIVE messages. This prevents committed plans from sitting behind a queue of workflow requests.

### Rationale

- Mailbox loop NEVER blocks, preserving responsiveness for all message types
- Context parking is simple (Dict lookup), with zero shared state concerns (single-threaded loop)
- Timeout reaper prevents context leaks from failed/slow planners
- Same pattern (park, await event, reap) reuses for HIL, making the architecture consistent
- CommittedPlan re-enters through the mailbox, maintaining the single-dequeue processing invariant from ORCH-005

---

## Alternatives Considered

### Alternative 1: Async Await with Background Task

**Rejected because:** `asyncio.create_task(await_plan())` runs concurrently with the mailbox loop, creating shared mutable state between the background task (building DAG) and the mailbox loop (processing other messages). Requires locks on PendingPlanContext and DAG state. Violates the single-threaded simplicity of ORCH-005.

### Alternative 2: Dedicated Planner Callback Thread

**Rejected because:** Thread-based callback introduces all thread-safety concerns rejected in ORCH-005. Callback must marshal back to the mailbox loop anyway (to access DAG state), so it adds complexity without benefit.

### Alternative 3: Synchronous Planning with Mailbox Pause

**Rejected because:** Blocking the mailbox for 45s is unacceptable. MEDIUM tasks would time out in their 10s envelope. Interrupts would be delayed. The entire Orchestrator would appear unresponsive.

---

## Consequences

### Positive

- Zero mailbox blocking -- MEDIUM, workflow, and interrupt processing continues during HIGH planning
- Single-threaded invariant preserved (no locks, no races)
- Timeout reaper prevents resource leaks from abandoned plans
- Pattern reusable for any future async request-response protocol (HIL, sub-workflow)

### Negative

- Planning gap means SessionState snapshot may be stale when DAG finally executes (mitigated by wave-boundary re-read per ORCH-011 Q4)
- Orphan plans (arriving after timeout) are discarded -- no automatic retry (Concierge decides)
- Context parking adds memory usage proportional to concurrent pending plans (bounded by timeout reaper)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Context leak (reaper bug) | Low | Medium | Telemetry counter for parked contexts; alert if count > threshold |
| Stale snapshot causes wrong DAG decisions | Low | Medium | Wave-boundary safety_band re-read; DAG steps are Fabric calls (fresh data) |
| Multiple HIGHs exhaust memory | Very Low | Low | ConcurrencyGuard limits active DAGs; parking is lightweight (envelope + snapshot) |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| dispatch_high() | `k1/orchestrator/orchestration/orchestrator_service.py` | New |
| receive_plan() | `k1/orchestrator/orchestration/orchestrator_service.py` | New |
| PendingPlanContext | `k1/orchestrator/types.py` | New |
| PendingHILContext | `k1/orchestrator/types.py` | New |
| _reap_stale_contexts() | `k1/orchestrator/orchestration/orchestrator_service.py` | New |
| EventSubscriptionAdapter (plan routing) | `k1/orchestrator/adapters/event_subscription_adapter.py` | New |

### Success Metrics

- dispatch_high() returns in <1ms (parks and returns, no I/O blocking)
- MEDIUM tasks processed during HIGH planning (verified in integration test)
- Timeout reaper cleans stale contexts within 5s of timeout
- Zero orphan PendingPlanContext entries after test suite completion

### Testing Strategy

- [ ] Unit tests: dispatch_high() parks context + returns DEFERRED
- [ ] Unit tests: receive_plan() retrieves parked context + triggers DAG
- [ ] Unit tests: receive_plan() with unknown request_id -> discard
- [ ] Unit tests: timeout reaper expires stale context after 45s
- [ ] Integration tests: MEDIUM processed during HIGH planning gap
- [ ] Integration tests: InterruptRequest delivered during HIGH planning
- [ ] Stress tests: multiple HIGH tasks with overlapping plan times

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial decision -- event-driven context-parking model |
